from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
)


def candidate_only_iteration_run_with_hooks(
    *,
    cwd: str | Path | None,
    iteration: Any,
    assessment: RefinementCandidateAssessment,
    contract_regression_preservation: Any,
    load_session_fn: Callable[..., Any],
    save_session_fn: Callable[..., Any],
    apply_candidate_only_state_fn: Callable[..., Any],
    candidate_only_result_fn: Callable[..., dict[str, Any]],
    file_sha256_fn: Callable[..., str],
) -> RefinementIterationRun:
    state = load_session_fn(cwd)
    apply_candidate_only_state_fn(
        state,
        temp_state_paper=assessment.temp_state_paper,
        temp_latest_review=assessment.temp_latest_review,
        validation_path=assessment.validation_path,
        temp_review_history_len=assessment.temp_review_history_len,
    )
    save_session_fn(cwd, state)
    return RefinementIterationRun(
        result=candidate_only_result_fn(
            iteration=iteration.candidate_iter,
            score_before=assessment.previous_score,
            score_after=assessment.candidate_score,
            axis_scores_before=assessment.previous_axes,
            axis_scores_after=assessment.candidate_axes,
            paper_path=assessment.temp_state_paper,
            candidate_path=assessment.candidate_tex_path,
            candidate_sha256=file_sha256_fn(assessment.candidate_tex_path),
            worklog_path=assessment.worklog_path,
            compile_error=assessment.compile_error,
            validation_path=assessment.validation_path,
            validation_payload=assessment.validation_payload,
            review_path=assessment.candidate_review_path,
            no_op_refinement=assessment.no_op_refinement,
            contract_regression_preservation=contract_regression_preservation,
        ),
        stop_after=True,
    )


def accepted_iteration_run_with_hooks(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
    artifact_path_fn: Callable[..., Path],
    write_text_fn: Callable[..., Any],
    record_lane_manifest_fn: Callable[..., Path],
    load_session_fn: Callable[..., Any],
    save_session_fn: Callable[..., Any],
    apply_accepted_state_fn: Callable[..., Any],
    accepted_result_fn: Callable[..., dict[str, Any]],
) -> RefinementIterationRun:
    final_path = artifact_path_fn(cwd, "paper.full.tex")
    write_text_fn(final_path, assessment.latex)
    lane_path = record_lane_manifest_fn(
        cwd,
        runtime_mode=draft.runtime_mode,
        lane_type=draft.lane_type,
        fallback_used=draft.fallback_used,
        input_artifacts=[assessment.temp_state_paper, assessment.temp_latest_review or ""],
        output_artifacts=[str(final_path), str(assessment.worklog_path), str(assessment.validation_path)],
        notes=assessment.lane_notes,
    )
    state = load_session_fn(cwd)
    apply_accepted_state_fn(
        state,
        final_path=final_path,
        candidate_review_path=decision.candidate_review_path,
        candidate_pdf_path=assessment.candidate_pdf_path,
        iteration=draft.iteration.candidate_iter,
        previous_score=assessment.previous_score,
        candidate_score=decision.candidate_score,
        compile_preservation=assessment.compile_preservation,
        review_retry_scores=decision.review_retry_scores,
        lane_manifest_path=lane_path,
    )
    save_session_fn(cwd, state)
    return RefinementIterationRun(
        result=accepted_result_fn(
            iteration=draft.iteration.candidate_iter,
            compile_preservation=assessment.compile_preservation,
            score_before=assessment.previous_score,
            score_after=decision.candidate_score,
            paper_path=final_path,
            worklog_path=assessment.worklog_path,
            compile_error=assessment.preserved_compile_error,
            validation_path=assessment.validation_path,
            validation_payload=assessment.validation_payload,
            lane_manifest_path=lane_path,
            review_retry_paths=decision.review_retry_paths,
            review_retry_scores=decision.review_retry_scores,
        ),
        stop_after=False,
    )


def rejected_iteration_run_with_hooks(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
    record_lane_manifest_fn: Callable[..., Path],
    load_session_fn: Callable[..., Any],
    save_session_fn: Callable[..., Any],
    apply_rejected_state_fn: Callable[..., Any],
    rejected_result_fn: Callable[..., dict[str, Any]],
) -> RefinementIterationRun:
    lane_path = record_lane_manifest_fn(
        cwd,
        runtime_mode=draft.runtime_mode,
        lane_type=draft.lane_type,
        fallback_used=draft.fallback_used,
        compile_error=assessment.compile_error,
        input_artifacts=[assessment.temp_state_paper, assessment.temp_latest_review or ""],
        output_artifacts=[str(assessment.worklog_path), str(assessment.validation_path)],
        notes=assessment.lane_notes,
    )
    state = load_session_fn(cwd)
    reason = assessment.compile_error or "score_regressed_or_tie_break_failed"
    print(
        f"Refinement iter {draft.iteration.candidate_iter} rejected: score {assessment.previous_score} -> {decision.candidate_score}; reason={reason}",
        file=sys.stderr,
    )
    apply_rejected_state_fn(
        state,
        temp_state_paper=assessment.temp_state_paper,
        temp_latest_review=assessment.temp_latest_review,
        validation_path=assessment.validation_path,
        temp_review_history_len=assessment.temp_review_history_len,
        iteration=draft.iteration.candidate_iter,
        previous_score=assessment.previous_score,
        candidate_score=decision.candidate_score,
        review_retry_scores=decision.review_retry_scores,
        lane_manifest_path=lane_path,
    )
    save_session_fn(cwd, state)
    return RefinementIterationRun(
        result=rejected_result_fn(
            iteration=draft.iteration.candidate_iter,
            score_before=assessment.previous_score,
            score_after=decision.candidate_score,
            paper_path=assessment.temp_state_paper,
            worklog_path=assessment.worklog_path,
            compile_error=assessment.compile_error,
            validation_path=assessment.validation_path,
            validation_payload=assessment.validation_payload,
            lane_manifest_path=lane_path,
            review_retry_paths=decision.review_retry_paths,
            review_retry_scores=decision.review_retry_scores,
        ),
        stop_after=True,
    )


__all__ = [
    "accepted_iteration_run_with_hooks",
    "candidate_only_iteration_run_with_hooks",
    "rejected_iteration_run_with_hooks",
]
