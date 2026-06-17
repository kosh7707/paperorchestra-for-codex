from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_text
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion import _file_sha256
from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
    RefinementValidationOutcome,
)
from paperorchestra.engine.refine_manifests import (
    record_accepted_refinement_lane_manifest,
    record_rejected_refinement_lane_manifest,
)
from paperorchestra.engine.refine_persistence import (
    apply_accepted_refinement_state,
    apply_candidate_only_refinement_state,
    apply_rejected_refinement_state,
)
from paperorchestra.engine.refine_results import (
    accepted_refinement_result,
    candidate_only_result,
    contract_validation_failed_result,
    rejected_refinement_result,
)
from paperorchestra.engine.reports import _blocking_issues, _issue_messages, _record_validation_report


def record_refinement_validation_outcome(
    *,
    cwd: str | Path | None,
    state: Any,
    iteration: Any,
    validation_issues: list[Any],
    validation_name: str,
    latex: str,
) -> RefinementValidationOutcome:
    validation_path, validation_payload = _record_validation_report(
        cwd,
        stage="refinement",
        issues=validation_issues,
        name=validation_name,
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _blocking_issues(validation_issues)
    if not blocking_issues:
        if validation_issues:
            state.notes.append(
                f"Refinement iteration {state.refinement_iteration + 1} produced validation warnings: "
                + " | ".join(_issue_messages(validation_issues))
            )
        return RefinementValidationOutcome(
            validation_path=validation_path,
            validation_payload=validation_payload,
            failure_run=None,
        )

    result = contract_validation_failed_result(
        iteration=state.refinement_iteration + 1,
        score_before=state.review_history[-1].overall_score
        if state.review_history
        else float(iteration.review_payload.get("overall_score", 0.0)),
        paper_path=state.artifacts.paper_full_tex,
        issues=_issue_messages(blocking_issues),
        validation_path=validation_path,
        validation_payload=validation_payload,
    )
    state.notes.append(f"Rejected refinement iteration {state.refinement_iteration + 1} due to contract validation failure.")
    print(
        f"Refinement iter {state.refinement_iteration + 1} rejected: contract validation failed ({'; '.join(_issue_messages(blocking_issues))})",
        file=sys.stderr,
    )
    save_session(cwd, state)
    return RefinementValidationOutcome(
        validation_path=validation_path,
        validation_payload=validation_payload,
        failure_run=RefinementIterationRun(result=result, stop_after=True),
    )


def candidate_only_iteration_run(
    *,
    cwd: str | Path | None,
    iteration: Any,
    assessment: RefinementCandidateAssessment,
    contract_regression_preservation: Any,
) -> RefinementIterationRun:
    state = load_session(cwd)
    apply_candidate_only_refinement_state(
        state,
        temp_state_paper=assessment.temp_state_paper,
        temp_latest_review=assessment.temp_latest_review,
        validation_path=assessment.validation_path,
        temp_review_history_len=assessment.temp_review_history_len,
    )
    save_session(cwd, state)
    return RefinementIterationRun(
        result=candidate_only_result(
            iteration=iteration.candidate_iter,
            score_before=assessment.previous_score,
            score_after=assessment.candidate_score,
            axis_scores_before=assessment.previous_axes,
            axis_scores_after=assessment.candidate_axes,
            paper_path=assessment.temp_state_paper,
            candidate_path=assessment.candidate_tex_path,
            candidate_sha256=_file_sha256(assessment.candidate_tex_path),
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


def accepted_iteration_run(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
) -> RefinementIterationRun:
    final_path = artifact_path(cwd, "paper.full.tex")
    write_text(final_path, assessment.latex)
    lane_path = record_accepted_refinement_lane_manifest(
        cwd,
        runtime_mode=draft.runtime_mode,
        lane_type=draft.lane_type,
        fallback_used=draft.fallback_used,
        input_artifacts=[assessment.temp_state_paper, assessment.temp_latest_review or ""],
        output_artifacts=[str(final_path), str(assessment.worklog_path), str(assessment.validation_path)],
        notes=assessment.lane_notes,
    )
    state = load_session(cwd)
    apply_accepted_refinement_state(
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
    save_session(cwd, state)
    return RefinementIterationRun(
        result=accepted_refinement_result(
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


def rejected_iteration_run(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
) -> RefinementIterationRun:
    lane_path = record_rejected_refinement_lane_manifest(
        cwd,
        runtime_mode=draft.runtime_mode,
        lane_type=draft.lane_type,
        fallback_used=draft.fallback_used,
        compile_error=assessment.compile_error,
        input_artifacts=[assessment.temp_state_paper, assessment.temp_latest_review or ""],
        output_artifacts=[str(assessment.worklog_path), str(assessment.validation_path)],
        notes=assessment.lane_notes,
    )
    state = load_session(cwd)
    reason = assessment.compile_error or "score_regressed_or_tie_break_failed"
    print(
        f"Refinement iter {draft.iteration.candidate_iter} rejected: score {assessment.previous_score} -> {decision.candidate_score}; reason={reason}",
        file=sys.stderr,
    )
    apply_rejected_refinement_state(
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
    save_session(cwd, state)
    return RefinementIterationRun(
        result=rejected_refinement_result(
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
