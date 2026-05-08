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
    _read_json,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
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

def _repair_prompt(current_paper: str, citation_map: dict[str, Any], issues: list[dict[str, Any]]) -> tuple[str, str]:
    system_prompt = """
You are a bounded PaperOrchestra citation-claim repair writer.
Revise only cited sentences listed in the issue packet.
Do not add new citations outside citation_map.json.
Do not add new empirical results, proof claims, or external facts.
Prefer softening, splitting, or removing unsupported cited claims.
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

Rules:
- Preserve unrelated sections.
- Preserve existing labels, figure paths, and bibliography hook.
- Use only citation keys already present in citation_map.json.
- Do not include reviewer numeric scores.
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
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before repairing citation claims.")
    mutation_snapshot = _session_mutation_snapshot(state)
    review_path = Path(citation_review_path).resolve() if citation_review_path else Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    citation_review = _read_json(review_path)
    if not isinstance(citation_review, dict):
        raise ContractError(f"Citation review is not available: {review_path}")
    issues = _non_supported_citation_items(citation_review)
    result: dict[str, Any] = {
        "schema_version": "citation-claim-repair/1",
        "started_at": utc_now_iso(),
        "citation_review": str(review_path),
        "issue_count": len(issues),
        "accepted": False,
        "reason": None,
    }
    if not issues:
        result.update({"accepted": True, "reason": "no_non_supported_citation_claims", "completed_at": utc_now_iso()})
        return result
    paper_path = Path(state.artifacts.paper_full_tex)
    original = paper_path.read_text(encoding="utf-8")
    citation_map = _read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    if not isinstance(citation_map, dict):
        citation_map = {}
    system_prompt, user_prompt = _repair_prompt(original, citation_map, issues)
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
    paper_path.write_text(candidate, encoding="utf-8")
    validation_path, validation_payload = record_current_validation_report(cwd, name="validation.citation-repair.json")
    result["validation"] = {"path": str(validation_path), "ok": validation_payload.get("ok"), "blocking_issue_count": validation_payload.get("blocking_issue_count")}
    if not validation_payload.get("ok"):
        paper_path.write_text(original, encoding="utf-8")
        _restore_session_mutation_snapshot(cwd, mutation_snapshot)
        result.update({"reason": "validation_failed", "completed_at": utc_now_iso()})
        return result
    if require_compile:
        try:
            pdf_path = compile_current_paper(cwd)
            result["compile"] = {"ok": True, "pdf": str(pdf_path)}
        except Exception as exc:
            paper_path.write_text(original, encoding="utf-8")
            _restore_session_mutation_snapshot(cwd, mutation_snapshot)
            result["compile"] = {"ok": False, "error": str(exc)}
            result.update({"reason": "compile_failed", "completed_at": utc_now_iso()})
            return result
    if not commit:
        paper_path.write_text(original, encoding="utf-8")
        _restore_session_mutation_snapshot(cwd, mutation_snapshot)
    state = load_session(cwd)
    state.notes.append("Citation-claim repair candidate accepted." + (" Committed." if commit else " Awaiting citation-support approval."))
    save_session(cwd, state)
    result.update({"accepted": True, "committed": commit, "reason": "accepted", "completed_at": utc_now_iso()})
    return result
