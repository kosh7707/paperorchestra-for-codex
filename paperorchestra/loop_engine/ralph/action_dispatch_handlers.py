from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from paperorchestra.core.session import load_session
from paperorchestra.engine.planning_stages import plan_narrative_and_claims
from paperorchestra.engine.refine_stages import refine_current_paper
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.manuscript.source_obligations import write_source_obligations
from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.loop_engine.quality.loop import CITATION_SUPPORT_REVIEW_REFRESH_CODES, REVIEW_REFRESH_CODES
from paperorchestra.loop_engine.ralph.citation_candidate_preservation import preserve_citation_candidate_for_approval
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.loop_engine.ralph.artifacts import (
    _refresh_citation_integrity_for_current_manuscript,
    _try_rebuild_bib_for_citation_quality,
)
from paperorchestra.loop_engine.ralph.repair import repair_citation_claims
from paperorchestra.loop_engine.ralph.semantic_recheck import _citation_repair_failure_payload
from paperorchestra.loop_engine.ralph.state import _artifact_sha, guarded_replace_manuscript_text

ActionHandler = Callable[[str, dict[str, Any], QaLoopActionDispatchContext, _QaLoopActionDispatchState], bool]

NARRATIVE_PLAN_CODES = {
    "narrative_plan_missing",
    "claim_map_missing",
    "citation_placement_plan_missing",
    "narrative_plan_stale",
    "claim_map_stale",
    "citation_placement_plan_stale",
}
VALIDATION_REFRESH_CODES = {"validation_report_missing", "validation_report_stale"}
FIGURE_PLACEMENT_REVIEW_CODES = {"figure_placement_review_missing", "figure_placement_review_stale"}
CITATION_SUPPORT_REVIEW_CODES = CITATION_SUPPORT_REVIEW_REFRESH_CODES | {"citation_support_evidence_research_needed"}
CITATION_QUALITY_REFRESH_CODES = {
    "critical_unknown_reference",
    "critical_missing_bib_entry",
    "critical_unsupported_citation",
    "critical_citation_support_missing",
    "critical_weak_reference_identity",
}
CITATION_INTEGRITY_REFRESH_CODES = {
    "rendered_reference_audit_missing",
    "rendered_reference_audit_stale",
    "citation_intent_plan_missing",
    "citation_intent_plan_stale",
    "citation_source_match_missing",
    "citation_source_match_stale",
    "citation_integrity_missing",
    "citation_integrity_stale",
    "citation_critic_missing",
    "citation_critic_stale",
}
COMPILE_CODES = {
    "compile_report_missing",
    "compile_report_stale",
    "compile_report_legacy_untrusted",
    "compile_pdf_missing",
    "compile_pdf_stale",
    "compile_not_clean",
}
SECTION_REVIEW_CODES = {"section_review_missing", "section_review_stale", "section_review_legacy_untrusted"}
SOURCE_OBLIGATION_CODES = {"source_obligations_missing", "source_obligations_stale"}
REFINE_CODES = {
    "review_score_below_threshold",
    "section_quality_below_threshold",
    "source_material_coverage_insufficient",
}
CITATION_REPAIR_CODES = {
    "citation_support_critic_failed",
    "citation_density_policy_failed",
    "citation_coverage_insufficient",
    "high_risk_uncited_claim",
}


def _handle_narrative_plan(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    paths = plan_narrative_and_claims(context.cwd, provider=None, runtime_mode=context.runtime_mode)
    execution["actions_attempted"].append(
        {"code": code, "handler": "plan_narrative", "paths": {key: str(path) for key, path in paths.items()}}
    )
    return True


def _handle_validation_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    validation_path, validation_payload = record_current_validation_report(
        context.cwd,
        name="validation.qa-loop-step.precondition.json",
    )
    execution["actions_attempted"].append(
        {"code": code, "handler": "validate_current", "path": str(validation_path), "ok": validation_payload.get("ok")}
    )
    return True


def _handle_figure_placement_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    figure_path, figure_payload = write_figure_placement_review(context.cwd)
    warning_count = (
        (figure_payload.get("summary") or {}).get("warning_count")
        if isinstance(figure_payload, dict)
        else None
    )
    execution["actions_attempted"].append(
        {"code": code, "handler": "review_figure_placement", "path": str(figure_path), "warning_count": warning_count}
    )
    return True


def _handle_citation_support_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    review_path = write_citation_support_review(
        context.cwd,
        provider=context.citation_provider,
        evidence_mode=context.citation_evidence_mode,
    )
    execution["actions_attempted"].append({"code": code, "handler": "critique_citations", "path": str(review_path)})
    return True


def _handle_citation_quality_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    bibtex_rebuild = (
        _try_rebuild_bib_for_citation_quality(context.cwd)
        if code == "critical_weak_reference_identity"
        else None
    )
    review_path = write_citation_support_review(
        context.cwd,
        provider=context.citation_provider,
        evidence_mode=context.citation_evidence_mode,
    )
    refreshed = _refresh_citation_integrity_for_current_manuscript(context.cwd, quality_mode=context.quality_mode)
    attempted: dict[str, Any] = {
        "code": code,
        "handler": "refresh_citation_quality",
        "citation_support_review": str(review_path),
        "citation_integrity": refreshed,
    }
    if bibtex_rebuild is not None:
        attempted["bibtex_rebuild"] = bibtex_rebuild
    execution["actions_attempted"].append(attempted)
    return True


def _handle_citation_integrity_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    refreshed = _refresh_citation_integrity_for_current_manuscript(context.cwd, quality_mode=context.quality_mode)
    execution["actions_attempted"].append(
        {"code": code, "handler": "refresh_citation_integrity", "artifacts": refreshed}
    )
    return True


def _handle_review_refresh(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = review_current_paper(context.cwd, context.provider, runtime_mode=context.runtime_mode)
    execution["actions_attempted"].append({"code": code, "handler": "review", "path": str(path)})
    return True


def _handle_compile(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    try:
        pdf_path = compile_current_paper(context.cwd)
    except Exception as exc:
        execution["actions_attempted"].append({"code": code, "handler": "compile", "ok": False, "error": str(exc)})
        return False
    execution["actions_attempted"].append({"code": code, "handler": "compile", "pdf": str(pdf_path), "ok": True})
    return True


def _handle_section_review(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = write_section_review(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "critique_sections", "path": str(path)})
    return True


def _handle_source_obligations(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    path = write_source_obligations(context.cwd)
    execution["actions_attempted"].append({"code": code, "handler": "build_source_obligations", "path": str(path)})
    return True


def _handle_refine(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    session = load_session(context.cwd)
    if not session.artifacts.latest_review_json:
        review_path = review_current_paper(context.cwd, context.provider, runtime_mode=context.runtime_mode)
        execution["actions_attempted"].append(
            {"code": code, "handler": "review", "path": str(review_path), "reason": "required_before_refine"}
        )
    refine_result = refine_current_paper(
        context.cwd,
        context.provider,
        iterations=1,
        require_compile_for_accept=context.require_compile,
        runtime_mode=context.runtime_mode,
        claim_safe=context.quality_mode == "claim_safe",
    )
    section_path = write_section_review(context.cwd)
    execution["actions_attempted"].append(
        {"code": code, "handler": "refine", "result": refine_result, "section_review": str(section_path)}
    )
    return not any(not item.get("accepted", False) for item in refine_result)


def _handle_citation_repair(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    repair = repair_citation_claims(
        context.cwd,
        context.provider,
        runtime_mode=context.runtime_mode,
        require_compile=context.require_compile,
        commit=False,
    )
    if not repair.get("accepted"):
        failure = _citation_repair_failure_payload(code, repair)
        execution.setdefault("repair_failures", []).append(failure)
        execution["actionable_failure"] = {
            "category": "citation_repair_failed",
            "code": code,
            "reason": failure["reason"],
            "validation_failing_codes": failure["validation"]["failing_codes"],
            "semantic_recheck_blockers": failure.get("semantic_recheck_blockers") or [],
            "next_steps": failure["next_steps"],
        }
        execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
        return False
    if context.paper_path and repair.get("candidate_path"):
        preserved_candidate_path = preserve_citation_candidate_for_approval(context.cwd, repair.get("candidate_path"))
        if preserved_candidate_path:
            repair = dict(repair)
            repair.setdefault("raw_candidate_path", str(repair.get("candidate_path")))
            repair["candidate_path"] = preserved_candidate_path
            repair["candidate_sha256"] = _artifact_sha(preserved_candidate_path)
        state.citation_candidate_path = str(repair["candidate_path"])
        guarded_replace_manuscript_text(
            context.cwd,
            context.paper_path,
            Path(state.citation_candidate_path).read_text(encoding="utf-8"),
            reason="qa_loop_citation_candidate_for_validation",
            original_text=context.original_paper,
        )
        state.citation_candidate_applied = True
    execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
    return True


ACTION_HANDLER_REGISTRY: tuple[tuple[frozenset[str], ActionHandler], ...] = (
    (frozenset(NARRATIVE_PLAN_CODES), _handle_narrative_plan),
    (frozenset(VALIDATION_REFRESH_CODES), _handle_validation_refresh),
    (frozenset(FIGURE_PLACEMENT_REVIEW_CODES), _handle_figure_placement_review),
    (frozenset(CITATION_SUPPORT_REVIEW_CODES), _handle_citation_support_review),
    (frozenset(CITATION_QUALITY_REFRESH_CODES), _handle_citation_quality_refresh),
    (frozenset(CITATION_INTEGRITY_REFRESH_CODES), _handle_citation_integrity_refresh),
    (frozenset(REVIEW_REFRESH_CODES), _handle_review_refresh),
    (frozenset(COMPILE_CODES), _handle_compile),
    (frozenset(SECTION_REVIEW_CODES), _handle_section_review),
    (frozenset(SOURCE_OBLIGATION_CODES), _handle_source_obligations),
    (frozenset(REFINE_CODES), _handle_refine),
    (frozenset(CITATION_REPAIR_CODES), _handle_citation_repair),
)


def handled_action_codes() -> set[str]:
    return {code for codes, _handler in ACTION_HANDLER_REGISTRY for code in codes}


def handler_for_code(code: str) -> ActionHandler | None:
    for codes, handler in ACTION_HANDLER_REGISTRY:
        if code in codes:
            return handler
    return None
