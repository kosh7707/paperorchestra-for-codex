from __future__ import annotations

from typing import Any

from dataclasses import replace

from paperorchestra.loop_engine.ralph.bridge_candidate_models import (
    CandidateResolutionRequest,
    CandidateResolutionResult,
    PostActionState,
)
from paperorchestra.loop_engine.ralph.bridge_candidate_updates import (
    apply_restored_current,
    baseline_candidate_result,
    with_candidate_updates,
)
from paperorchestra.loop_engine.ralph.bridge_restore import _restore_current_after_uncommitted_candidate
from paperorchestra.loop_engine.ralph.candidate_outcomes import (
    build_auto_commit_record,
    build_auto_commit_rejection_records,
    build_citation_support_rejection_records,
)
from paperorchestra.loop_engine.ralph.state import clear_pending_manuscript_write


def _baseline_result(state: PostActionState) -> CandidateResolutionResult:
    return baseline_candidate_result(state)


def _restore_current_candidate(request: CandidateResolutionRequest, *, validation_name: str) -> dict[str, Any] | None:
    return _restore_current_after_uncommitted_candidate(
        request.cwd,
        paper_path=request.paper_path,
        original_paper=request.original_paper,
        mutation_snapshot=request.mutation_snapshot,
        citation_review_snapshot=request.citation_review_snapshot,
        citation_trace_snapshot=request.citation_trace_snapshot,
        require_compile=request.require_compile,
        require_live_verification=request.require_live_verification,
        quality_mode=request.quality_mode,
        max_iterations=request.max_iterations,
        accept_mixed_provenance=request.accept_mixed_provenance,
        before_eval=request.before_eval,
        before_summary=request.before_summary,
        actions_attempted=request.actions_attempted,
        validation_name=validation_name,
    )


def _apply_restored_current(result: CandidateResolutionResult, restored: dict[str, Any] | None) -> CandidateResolutionResult:
    return apply_restored_current(result, restored)


def _with_updates(result: CandidateResolutionResult, **updates: Any) -> CandidateResolutionResult:
    return with_candidate_updates(result, **updates)


def resolve_candidate_outcome(
    request: CandidateResolutionRequest,
    state: PostActionState,
) -> CandidateResolutionResult:
    result = _baseline_result(state)
    if request.candidate_outcome == "none":
        return result
    if request.candidate_outcome == "auto_commit":
        clear_pending_manuscript_write(
            request.cwd,
            status="resolved",
            reason="qa_loop_progressive_citation_candidate_committed",
        )
        return _with_updates(
            result,
            candidate_state=request.candidate_state,
            candidate_progress=request.candidate_progress,
            candidate_auto_commit=build_auto_commit_record(
                candidate_path=request.candidate_path,
                auto_commit_reason=request.auto_commit_reason,
                residual_citation_failures=request.residual_citation_failures,
                after_codes=request.after_codes,
            ),
        )

    if request.candidate_outcome == "citation_support_rejected":
        result = _apply_restored_current(
            result,
            _restore_current_candidate(request, validation_name="validation.qa-loop-step.rollback.json"),
        )
        rejection = build_citation_support_rejection_records(
            candidate_path=request.candidate_path,
            residual_citation_failures=request.residual_citation_failures,
            auto_commit_reason=request.auto_commit_reason,
        )
        return _with_updates(
            replace(result, verdict="human_needed"),
            candidate_rollback=rejection["rollback"],
            candidate_state=request.candidate_state,
            candidate_progress=request.candidate_progress,
            candidate_handoff=rejection["handoff"],
        )

    if request.candidate_outcome == "auto_commit_gate_rejected":
        result = _apply_restored_current(
            result,
            _restore_current_candidate(
                request,
                validation_name="validation.qa-loop-step.candidate-approved-original-restored.json",
            ),
        )
        rejection = build_auto_commit_rejection_records(
            candidate_path=request.candidate_path,
            auto_commit_reason=request.auto_commit_reason,
            after_codes=request.after_codes,
        )
        return _with_updates(
            replace(result, verdict="human_needed"),
            candidate_rollback=rejection["rollback"],
            candidate_handoff=rejection["handoff"],
            candidate_state=request.candidate_state,
            candidate_progress=request.candidate_progress,
        )

    raise ValueError(f"Unsupported candidate outcome: {request.candidate_outcome}")
