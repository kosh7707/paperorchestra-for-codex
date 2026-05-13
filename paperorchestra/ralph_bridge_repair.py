from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import extract_latex
from .models import utc_now_iso
from .pipeline import (
    ContractError,
    _build_completion_request,
    _complete_with_runtime_mode,
    compile_current_paper,
    record_current_validation_report,
)
from .providers import BaseProvider
from .ralph_bridge_state import (
    NON_SUPPORTED_CITATION_STATUSES,
    atomic_write_text,
    clear_pending_manuscript_write,
    guarded_replace_manuscript_text,
    _read_json,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    recover_pending_manuscript_write,
)
from .session import artifact_path, load_session, save_session
from .validator import extract_citation_keys


def _non_supported_citation_items(citation_review: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in citation_review.get("items") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("support_status") or "") in NON_SUPPORTED_CITATION_STATUSES:
            result.append(item)
    return result

def _truncate_issue_text(value: Any, *, limit: int = 900) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."

def _citation_density_repair_issues(cwd: str | Path | None, *, limit: int = 16) -> list[dict[str, Any]]:
    audit_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        audit = _read_json(audit_path)
    except Exception:
        return []
    if not isinstance(audit, dict):
        return []
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    issues: list[dict[str, Any]] = []
    for item in density.get("bomb_sentences") or []:
        if not isinstance(item, dict):
            continue
        keys = [str(key) for key in item.get("citation_keys") or [] if str(key).strip()]
        issues.append(
            {
                "issue_type": "citation_bomb_sentence",
                "id": item.get("id"),
                "sentence": _truncate_issue_text(item.get("sentence")),
                "citation_keys": keys,
                "citation_count": len(keys),
                "required_action": "split the sentence, remove redundant references, or scope the claim without adding bibliography keys",
            }
        )
        if len(issues) >= limit:
            return issues
    for index, keys in enumerate(density.get("bomb_paragraph_key_sets") or [], start=1):
        if not isinstance(keys, list):
            continue
        normalized = [str(key) for key in keys if str(key).strip()]
        issues.append(
            {
                "issue_type": "citation_bomb_paragraph",
                "id": f"citation-bomb-paragraph-{index}",
                "citation_keys": normalized,
                "citation_count": len(normalized),
                "required_action": "distribute citations across claim-specific sentences or remove redundant references",
            }
        )
        if len(issues) >= limit:
            break
    return issues

def _high_risk_repair_issues(cwd: str | Path | None, *, limit: int = 16) -> list[dict[str, Any]]:
    quality_path = artifact_path(cwd, "quality-eval.json")
    try:
        quality_eval = _read_json(quality_path)
    except Exception:
        return []
    if not isinstance(quality_eval, dict):
        return []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else {}
    issues: list[dict[str, Any]] = []
    for item in sweep.get("items") or []:
        if not isinstance(item, dict):
            continue
        issues.append(
            {
                "issue_type": "high_risk_uncited_claim",
                "line": item.get("line"),
                "sentence": _truncate_issue_text(item.get("sentence")),
                "reason": _truncate_issue_text(item.get("reason"), limit=500),
                "required_action": "ground with existing verified evidence, scope as a limitation/author-material claim, or delete",
            }
        )
        if len(issues) >= limit:
            break
    return issues

def _claim_safety_repair_issues(cwd: str | Path | None) -> list[dict[str, Any]]:
    return _citation_density_repair_issues(cwd) + _high_risk_repair_issues(cwd)

def _repair_prompt(
    current_paper: str,
    citation_map: dict[str, Any],
    issues: list[dict[str, Any]],
    claim_safety_issues: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    system_prompt = """
You are a bounded PaperOrchestra citation-claim repair writer.
Revise only sentences listed in the citation or claim-safety issue packet.
Do not add new citations outside citation_map.json.
Do not add new empirical results, proof claims, or external facts.
Prefer softening, splitting, or removing unsupported cited claims, citation-dense sentences, and high-risk uncited claims.
Return the full revised LaTeX manuscript only.
""".strip()
    user_prompt = f"""
<DATA_BLOCK name="paper.tex">
{current_paper}
</DATA_BLOCK>

<DATA_BLOCK name="citation_map.json">
{json.dumps(citation_map, indent=2, ensure_ascii=False)}
</DATA_BLOCK>

<DATA_BLOCK name="citation_support_issues.json">
{json.dumps(issues, indent=2, ensure_ascii=False)}
</DATA_BLOCK>

<DATA_BLOCK name="claim_safety_repair_issues.json">
{json.dumps(claim_safety_issues or [], indent=2, ensure_ascii=False)}
</DATA_BLOCK>

Rules:
- Preserve unrelated sections.
- Preserve existing labels, figure paths, and bibliography hook.
- Use only citation keys already present in citation_map.json.
- Do not include reviewer numeric scores.
- For citation-density issues, split citation-bomb sentences, remove redundant references, or place citations on the exact supported sentence.
- For high-risk uncited claims, ground with existing verified evidence, scope as a limitation/author-material claim, or delete the claim.
""".strip()
    return system_prompt, user_prompt

def repair_citation_claims(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    citation_review_path: str | Path | None = None,
    runtime_mode: str = "compatibility",
    require_compile: bool = False,
    commit: bool = False,
) -> dict[str, Any]:
    recover_pending_manuscript_write(cwd)
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before repairing citation claims.")
    mutation_snapshot = _session_mutation_snapshot(state)
    review_path = Path(citation_review_path).resolve() if citation_review_path else Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    citation_review = _read_json(review_path)
    if not isinstance(citation_review, dict):
        raise ContractError(f"Citation review is not available: {review_path}")
    issues = _non_supported_citation_items(citation_review)
    claim_safety_issues = _claim_safety_repair_issues(cwd)
    result: dict[str, Any] = {
        "schema_version": "citation-claim-repair/1",
        "started_at": utc_now_iso(),
        "citation_review": str(review_path),
        "issue_count": len(issues),
        "claim_safety_issue_count": len(claim_safety_issues),
        "accepted": False,
        "reason": None,
    }
    if not issues and not claim_safety_issues:
        result.update({"accepted": True, "reason": "no_citation_claim_or_claim_safety_issues", "completed_at": utc_now_iso()})
        return result
    paper_path = Path(state.artifacts.paper_full_tex)
    original = paper_path.read_text(encoding="utf-8")
    citation_map = _read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    if not isinstance(citation_map, dict):
        citation_map = {}
    system_prompt, user_prompt = _repair_prompt(original, citation_map, issues, claim_safety_issues)
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=system_prompt, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="citation_claim_repair",
    )
    candidate = extract_latex(response)
    allowed_keys = set(citation_map.keys())
    unknown = sorted(set(extract_citation_keys(candidate)) - allowed_keys)
    candidate_path = artifact_path(cwd, "paper.citation-repair.candidate.tex")
    candidate_path.write_text(candidate, encoding="utf-8")
    result.update(
        {
            "candidate_path": str(candidate_path),
            "lane_type": lane_type,
            "fallback_used": fallback_used,
            "lane_notes": lane_notes,
            "unknown_citation_keys": unknown,
        }
    )
    if unknown:
        result.update({"reason": "unknown_citation_keys", "completed_at": utc_now_iso()})
        return result
    guarded_replace_manuscript_text(
        cwd,
        paper_path,
        candidate,
        reason="citation_repair_candidate_validation",
        original_text=original,
    )
    validation_path, validation_payload = record_current_validation_report(cwd, name="validation.citation-repair.json")
    result["validation"] = {"path": str(validation_path), "ok": validation_payload.get("ok"), "blocking_issue_count": validation_payload.get("blocking_issue_count")}
    if not validation_payload.get("ok"):
        atomic_write_text(paper_path, original)
        clear_pending_manuscript_write(cwd, status="restored", reason="citation_repair_validation_failed")
        _restore_session_mutation_snapshot(cwd, mutation_snapshot)
        result.update({"reason": "validation_failed", "completed_at": utc_now_iso()})
        return result
    if require_compile:
        try:
            pdf_path = compile_current_paper(cwd)
            result["compile"] = {"ok": True, "pdf": str(pdf_path)}
        except Exception as exc:
            atomic_write_text(paper_path, original)
            clear_pending_manuscript_write(cwd, status="restored", reason="citation_repair_compile_failed")
            _restore_session_mutation_snapshot(cwd, mutation_snapshot)
            result["compile"] = {"ok": False, "error": str(exc)}
            result.update({"reason": "compile_failed", "completed_at": utc_now_iso()})
            return result
    if not commit:
        atomic_write_text(paper_path, original)
        clear_pending_manuscript_write(cwd, status="restored", reason="citation_repair_uncommitted_candidate_restored")
        _restore_session_mutation_snapshot(cwd, mutation_snapshot)
    else:
        clear_pending_manuscript_write(cwd, status="resolved", reason="citation_repair_candidate_committed")
    state = load_session(cwd)
    state.notes.append("Citation-claim repair candidate accepted." + (" Committed." if commit else " Awaiting citation-support approval."))
    save_session(cwd, state)
    result.update({"accepted": True, "committed": commit, "reason": "accepted", "completed_at": utc_now_iso()})
    return result
