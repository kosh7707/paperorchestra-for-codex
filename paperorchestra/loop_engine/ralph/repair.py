from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_integrity import build_citation_integrity_audit
from paperorchestra.core.io import extract_latex, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.engine.pipeline import (
    ContractError,
    _build_completion_request,
    _complete_with_runtime_mode,
    compile_current_paper,
    record_current_validation_report,
)
from paperorchestra.runtime.providers import BaseProvider
from ..quality.source_checks import _high_risk_claim_sweep
from .state import (
    NON_SUPPORTED_CITATION_STATUSES,
    atomic_write_text,
    clear_pending_manuscript_write,
    guarded_replace_manuscript_text,
    _read_json,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    recover_pending_manuscript_write,
)
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.source_obligations import evaluate_source_obligations, source_obligations_path
from paperorchestra.manuscript.validator import allowed_citation_keys, canonical_citation_map, canonicalize_citation_keys, extract_citation_keys


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

def _duplicate_support_repair_issues(cwd: str | Path | None, *, limit: int = 16, examples_per_key: int = 4) -> list[dict[str, Any]]:
    audit_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        audit = _read_json(audit_path)
    except Exception:
        return []
    if not isinstance(audit, dict):
        return []
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    duplicate_keys = [str(key).strip() for key in duplicate.get("duplicate_keys") or [] if str(key).strip()]
    if not duplicate_keys:
        return []
    review_path = artifact_path(cwd, "citation_support_review.json")
    try:
        citation_review = _read_json(review_path)
    except Exception:
        citation_review = {}
    items = citation_review.get("items") if isinstance(citation_review, dict) else []
    support_items = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    issues: list[dict[str, Any]] = []
    for key in duplicate_keys:
        matching_items: list[dict[str, Any]] = []
        for index, item in enumerate(support_items, start=1):
            keys = {str(candidate).strip() for candidate in item.get("citation_keys") or [] if str(candidate).strip()}
            if key not in keys:
                continue
            matching_items.append(
                {
                    "id": str(item.get("id") or f"citation-support-{index}"),
                    "sentence": _truncate_issue_text(item.get("sentence")),
                    "support_status": str(item.get("support_status") or "unknown"),
                    "claim_type": item.get("claim_type"),
                }
            )
        issues.append(
            {
                "issue_type": "citation_duplicate_support",
                "citation_key": key,
                "occurrence_count": len(matching_items) or None,
                "affected_items": matching_items[:examples_per_key],
                "required_action": "remove or redistribute redundant repeated uses of this citation key; preserve the citation only where it directly supports a distinct claim and do not add bibliography keys",
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
    return _citation_density_repair_issues(cwd) + _duplicate_support_repair_issues(cwd) + _high_risk_repair_issues(cwd)

def _source_obligation_repair_context(cwd: str | Path | None, *, limit: int = 48) -> dict[str, Any]:
    try:
        trust_report = evaluate_source_obligations(cwd)
    except Exception as exc:
        return {"available": False, "reason": "source_obligation_trust_check_error", "error_type": type(exc).__name__}
    trust_failing_codes = {
        str(code)
        for code in trust_report.get("failing_codes") or []
        if str(code).strip()
    } if isinstance(trust_report, dict) else {"source_obligations_missing"}
    untrusted_codes = {
        "source_obligations_missing",
        "source_obligations_stale",
        "source_obligations_legacy_untrusted",
    }
    if trust_failing_codes & untrusted_codes:
        return {
            "available": False,
            "reason": sorted(trust_failing_codes & untrusted_codes)[0],
            "failing_codes": sorted(trust_failing_codes),
        }
    try:
        path = source_obligations_path(cwd)
        payload = _read_json(path)
    except Exception:
        return {"available": False}
    if not isinstance(payload, dict):
        return {"available": False}
    obligations: list[dict[str, Any]] = []
    for obligation in payload.get("obligations") or []:
        if not isinstance(obligation, dict):
            continue
        obligations.append(
            {
                "id": obligation.get("id"),
                "type": obligation.get("type"),
                "expected_manuscript_area": obligation.get("expected_manuscript_area"),
                "required_terms": obligation.get("required_terms") or [],
                "numeric_tokens": obligation.get("numeric_tokens") or [],
                "excerpt_preview": _truncate_issue_text(obligation.get("excerpt_preview"), limit=360),
            }
        )
        if len(obligations) >= limit:
            break
    return {
        "available": True,
        "path": str(path),
        "obligation_count": len(payload.get("obligations") or []),
        "included_obligation_count": len(obligations),
        "obligations": obligations,
    }

def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()

def _citation_integrity_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
    bomb_sentence_count = len([item for item in density.get("bomb_sentences") or [] if isinstance(item, dict)])
    bomb_paragraph_count = len([item for item in density.get("bomb_paragraph_key_sets") or [] if isinstance(item, list)])
    duplicate_support_count = len([item for item in duplicate.get("duplicate_keys") or [] if str(item).strip()])
    total = bomb_sentence_count + bomb_paragraph_count + duplicate_support_count
    return {
        "status": str(payload.get("status") or "unknown"),
        "failing_codes": [str(code) for code in payload.get("failing_codes") or []],
        "citation_bomb_sentence_count": bomb_sentence_count,
        "citation_bomb_paragraph_count": bomb_paragraph_count,
        "duplicate_support_count": duplicate_support_count,
        "target_issue_count": total,
    }

def _citation_issue_metrics_from_packet(issues: list[dict[str, Any]]) -> dict[str, Any]:
    bomb_sentence_count = sum(1 for item in issues if item.get("issue_type") == "citation_bomb_sentence")
    bomb_paragraph_count = sum(1 for item in issues if item.get("issue_type") == "citation_bomb_paragraph")
    duplicate_support_count = sum(1 for item in issues if item.get("issue_type") == "citation_duplicate_support")
    total = bomb_sentence_count + bomb_paragraph_count + duplicate_support_count
    failing_codes: list[str] = []
    if bomb_sentence_count or bomb_paragraph_count:
        failing_codes.append("citation_bomb_detected")
    if duplicate_support_count:
        failing_codes.append("citation_duplicate_support")
    return {
        "status": "fail" if total else "pass",
        "failing_codes": failing_codes,
        "citation_bomb_sentence_count": bomb_sentence_count,
        "citation_bomb_paragraph_count": bomb_paragraph_count,
        "duplicate_support_count": duplicate_support_count,
        "target_issue_count": total,
    }

def _high_risk_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(payload.get("status") or "unknown"),
        "failing_codes": [str(code) for code in payload.get("failing_codes") or []],
        "item_count": int(payload.get("item_count") or len(payload.get("items") or [])),
    }

def _high_risk_issue_metrics_from_packet(issues: list[dict[str, Any]]) -> dict[str, Any]:
    count = sum(1 for item in issues if item.get("issue_type") == "high_risk_uncited_claim")
    return {
        "status": "fail" if count else "pass",
        "failing_codes": ["high_risk_uncited_claim"] if count else [],
        "item_count": count,
    }

def _canonical_high_risk_baseline(
    cwd: str | Path | None,
    *,
    original_manuscript_hash: str | None,
) -> tuple[dict[str, Any] | None, str]:
    quality_path = artifact_path(cwd, "quality-eval.json")
    try:
        quality_eval = _read_json(quality_path)
    except Exception:
        return None, "quality_eval_missing"
    if not isinstance(quality_eval, dict):
        return None, "quality_eval_missing"
    expected_hash = str(original_manuscript_hash or "").strip()
    if expected_hash and not expected_hash.startswith("sha256:"):
        expected_hash = "sha256:" + expected_hash
    recorded_hash = str(quality_eval.get("manuscript_hash") or "").strip()
    if expected_hash and recorded_hash and recorded_hash != expected_hash:
        return None, "quality_eval_stale_ignored"
    if expected_hash and not recorded_hash:
        return None, "quality_eval_unbound_ignored"
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else None
    if not isinstance(sweep, dict):
        return None, "quality_eval_high_risk_missing"
    return _high_risk_metrics(sweep), "quality_eval"


def _strictly_improves(before_count: int, after_count: int) -> bool:
    return before_count <= 0 or after_count < before_count

def _candidate_semantic_recheck(
    cwd: str | Path | None,
    *,
    claim_safety_issues: list[dict[str, Any]],
    quality_mode: str = "claim_safe",
    original_manuscript_hash: str | None = None,
) -> dict[str, Any]:
    citation_targeted = any(
        str(item.get("issue_type") or "").startswith("citation_bomb_")
        or item.get("issue_type") == "citation_duplicate_support"
        for item in claim_safety_issues
    )
    high_risk_targeted = any(item.get("issue_type") == "high_risk_uncited_claim" for item in claim_safety_issues)

    canonical_citation_path = artifact_path(cwd, "citation_integrity.audit.json")
    try:
        canonical_citation = _read_json(canonical_citation_path)
    except Exception:
        canonical_citation = {}
    citation_before = (
        _citation_integrity_metrics(canonical_citation)
        if isinstance(canonical_citation, dict) and canonical_citation
        else _citation_issue_metrics_from_packet(claim_safety_issues)
    )
    citation_after_payload = build_citation_integrity_audit(cwd, quality_mode=quality_mode)
    citation_after = _citation_integrity_metrics(citation_after_payload)
    citation_path = artifact_path(cwd, "citation-integrity.citation-repair.candidate.json")
    write_json(citation_path, citation_after_payload)

    high_risk_before, high_risk_baseline_source = _canonical_high_risk_baseline(
        cwd,
        original_manuscript_hash=original_manuscript_hash,
    )
    if high_risk_before is None:
        high_risk_before = _high_risk_issue_metrics_from_packet(claim_safety_issues)
        if high_risk_baseline_source in {"quality_eval_missing", "quality_eval_high_risk_missing"}:
            high_risk_baseline_source = "repair_packet"
    high_risk_after_payload = _high_risk_claim_sweep(load_session(cwd), evaluate_source_obligations(cwd))
    high_risk_after = _high_risk_metrics(high_risk_after_payload)
    high_risk_path = artifact_path(cwd, "high-risk-sweep.citation-repair.candidate.json")
    write_json(high_risk_path, high_risk_after_payload)

    citation_improved = (not citation_targeted) or _strictly_improves(
        int(citation_before.get("target_issue_count") or 0),
        int(citation_after.get("target_issue_count") or 0),
    )
    high_risk_improved = (not high_risk_targeted) or _strictly_improves(
        int(high_risk_before.get("item_count") or 0),
        int(high_risk_after.get("item_count") or 0),
    )
    status = "pass" if citation_improved and high_risk_improved else "fail"
    return {
        "status": status,
        "citation_integrity": {
            "targeted": citation_targeted,
            "path": str(citation_path),
            "sha256": _file_sha256(citation_path),
            "before": citation_before,
            "after": citation_after,
            "improved": citation_improved,
        },
        "high_risk_claim_sweep": {
            "targeted": high_risk_targeted,
            "baseline_source": high_risk_baseline_source,
            "path": str(high_risk_path),
            "sha256": _file_sha256(high_risk_path),
            "before": high_risk_before,
            "after": high_risk_after,
            "improved": high_risk_improved,
        },
    }

def _repair_prompt(
    current_paper: str,
    citation_map: dict[str, Any],
    issues: list[dict[str, Any]],
    claim_safety_issues: list[dict[str, Any]] | None = None,
    source_obligation_context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    system_prompt = """
You are a bounded PaperOrchestra citation-claim repair writer.
Revise only sentences listed in the citation or claim-safety issue packet.
Do not add new citations outside citation_map.json.
Do not add new empirical results, proof claims, or external facts.
Prefer softening, splitting, or removing unsupported cited claims, citation-dense sentences, redundant repeated citation support, and high-risk uncited claims.
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

<DATA_BLOCK name="source_obligations_context.json">
{json.dumps(source_obligation_context or {"available": False}, indent=2, ensure_ascii=False)}
</DATA_BLOCK>

Rules:
- Preserve unrelated sections.
- Preserve existing labels, figure paths, and bibliography hook.
- Use only citation keys already present in citation_map.json.
- Do not include reviewer numeric scores.
- Preserve author-material obligations in source_obligations_context.json. If a citation repair removes, weakens, or rewrites an author-material claim, keep the required terms/numeric tokens represented elsewhere with scoped wording instead of deleting the obligation silently.
- For citation-density issues, split dense citation bundles, remove redundant references, or place citations on the exact supported sentence.
- For duplicate-support issues, keep a repeated citation only where it directly supports a distinct claim; otherwise remove, redistribute, or merge the redundant support.
- For weakly_supported issues, apply the issue's suggested_fix narrowly. If the cited source supports only a weaker wording, rewrite the sentence to that weaker wording instead of adding citations.
- If a citation is attached to a paper-internal claim such as what this manuscript evaluates, instantiates, proves, or reports, remove the external citation from that internal claim unless citation_map evidence directly supports the external background portion.
- If an issue is only a bibliography-metadata correction and the cited evidence supports the sentence, do not change unrelated prose; leave bibliographic repair to the citation registry/metadata lane.
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
    prompt_citation_map = canonical_citation_map(citation_map)
    system_prompt, user_prompt = _repair_prompt(
        original,
        prompt_citation_map,
        issues,
        claim_safety_issues,
        _source_obligation_repair_context(cwd),
    )
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=system_prompt, user_prompt=user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="citation_claim_repair",
    )
    candidate = extract_latex(response)
    candidate, citation_replacements = canonicalize_citation_keys(candidate, citation_map)
    allowed_keys = allowed_citation_keys(citation_map)
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
            "citation_replacements": citation_replacements,
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
    try:
        semantic_recheck = _candidate_semantic_recheck(
            cwd,
            claim_safety_issues=claim_safety_issues,
            original_manuscript_hash=hashlib.sha256(original.encode("utf-8")).hexdigest(),
        )
    except Exception as exc:
        atomic_write_text(paper_path, original)
        clear_pending_manuscript_write(cwd, status="restored", reason="citation_repair_semantic_recheck_error")
        _restore_session_mutation_snapshot(cwd, mutation_snapshot)
        result["semantic_recheck"] = {
            "status": "error",
            "error_type": type(exc).__name__,
        }
        result.update({"reason": "semantic_recheck_error", "completed_at": utc_now_iso()})
        return result
    result["semantic_recheck"] = semantic_recheck
    if semantic_recheck.get("status") != "pass":
        atomic_write_text(paper_path, original)
        clear_pending_manuscript_write(cwd, status="restored", reason="citation_repair_semantic_recheck_failed")
        _restore_session_mutation_snapshot(cwd, mutation_snapshot)
        result.update({"reason": "semantic_recheck_failed", "completed_at": utc_now_iso()})
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
