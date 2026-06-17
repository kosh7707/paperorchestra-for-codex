from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.bridge_records import build_restored_bridge_update
from paperorchestra.loop_engine.ralph.bridge_restore import _restore_current_after_uncommitted_candidate
from paperorchestra.loop_engine.ralph.candidate_outcomes import (
    CandidateOutcome,
    build_auto_commit_record,
    build_auto_commit_rejection_records,
    build_citation_support_rejection_records,
)
from paperorchestra.loop_engine.ralph.state import clear_pending_manuscript_write


@dataclass(frozen=True)
class PostActionState:
    eval_path: str | Path
    eval_payload: dict[str, Any]
    plan_path: str | Path
    plan_payload: dict[str, Any]
    summary: dict[str, Any]
    progress: dict[str, Any]
    verification: dict[str, Any]
    verdict: str


@dataclass(frozen=True)
class CandidateResolutionRequest:
    cwd: str | Path | None
    paper_path: Path | None
    original_paper: str | None
    mutation_snapshot: dict[str, Any]
    citation_review_snapshot: dict[str, Any] | None
    citation_trace_snapshot: dict[str, Any] | None
    require_compile: bool
    require_live_verification: bool
    quality_mode: str
    max_iterations: int
    accept_mixed_provenance: bool
    before_eval: dict[str, Any]
    before_summary: dict[str, Any]
    actions_attempted: bool
    candidate_outcome: CandidateOutcome
    candidate_path: str | None
    candidate_state: dict[str, Any] | None
    candidate_progress: dict[str, Any]
    auto_commit_reason: str
    residual_citation_failures: list[str]
    after_codes: set[str]


@dataclass(frozen=True)
class CandidateResolutionResult:
    final_eval_path: str | Path
    final_eval: dict[str, Any]
    final_plan_path: str | Path
    final_plan: dict[str, Any]
    final_summary: dict[str, Any]
    final_progress: dict[str, Any]
    final_verification: dict[str, Any]
    verdict: str
    execution_updates: dict[str, Any] = field(default_factory=dict)


def _baseline_result(state: PostActionState) -> CandidateResolutionResult:
    return CandidateResolutionResult(
        final_eval_path=state.eval_path,
        final_eval=state.eval_payload,
        final_plan_path=state.plan_path,
        final_plan=state.plan_payload,
        final_summary=state.summary,
        final_progress=state.progress,
        final_verification=state.verification,
        verdict=state.verdict,
    )


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
    if not restored:
        return result
    restored_update = build_restored_bridge_update(restored)
    updates = dict(result.execution_updates)
    updates.update(restored_update["execution_updates"])
    return replace(
        result,
        final_eval_path=restored_update["final_eval_path"],
        final_eval=restored_update["final_eval"],
        final_plan_path=restored_update["final_plan_path"],
        final_plan=restored_update["final_plan"],
        final_summary=restored_update["final_summary"],
        final_progress=restored_update["final_progress"],
        final_verification=restored_update["final_verification"],
        execution_updates=updates,
    )


def _with_updates(result: CandidateResolutionResult, **updates: Any) -> CandidateResolutionResult:
    merged = dict(result.execution_updates)
    merged.update(updates)
    return replace(result, execution_updates=merged)


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
