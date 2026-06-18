from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.core.io import extract_latex
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.errors import ContractError
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
)
from paperorchestra.engine.review_stages import compile_current_paper, record_current_validation_report
from paperorchestra.runtime.providers import BaseProvider
from paperorchestra.loop_engine.ralph.repair_issue_packet import (
    _claim_safety_repair_issues,
    _non_supported_citation_items,
    _source_obligation_repair_context,
)
from paperorchestra.loop_engine.ralph.repair_prompt import _repair_prompt
from paperorchestra.loop_engine.ralph.repair_recheck import (
    _candidate_semantic_recheck,
)
from .state import (
    atomic_write_text,
    clear_pending_manuscript_write,
    guarded_replace_manuscript_text,
    _read_json,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    recover_pending_manuscript_write,
)
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.validator import allowed_citation_keys, canonical_citation_map, canonicalize_citation_keys, extract_citation_keys


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
