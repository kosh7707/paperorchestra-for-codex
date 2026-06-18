from __future__ import annotations

import sys
from pathlib import Path

from paperorchestra.core.session import load_session as _load_session, save_session as _save_session
from paperorchestra.engine.refine_iteration_outcome_dependencies import _outcome_dependency
from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
)
from paperorchestra.engine.refine_manifests import record_rejected_refinement_lane_manifest as _record_rejected_refinement_lane_manifest
from paperorchestra.engine.refine_persistence import apply_rejected_refinement_state as _apply_rejected_refinement_state
from paperorchestra.engine.refine_results import rejected_refinement_result as _rejected_refinement_result


def rejected_iteration_run(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
) -> RefinementIterationRun:
    lane_path = _outcome_dependency(
        "record_rejected_refinement_lane_manifest",
        _record_rejected_refinement_lane_manifest,
    )(
        cwd,
        runtime_mode=draft.runtime_mode,
        lane_type=draft.lane_type,
        fallback_used=draft.fallback_used,
        compile_error=assessment.compile_error,
        input_artifacts=[assessment.temp_state_paper, assessment.temp_latest_review or ""],
        output_artifacts=[str(assessment.worklog_path), str(assessment.validation_path)],
        notes=assessment.lane_notes,
    )
    state = _outcome_dependency("load_session", _load_session)(cwd)
    reason = assessment.compile_error or "score_regressed_or_tie_break_failed"
    print(
        f"Refinement iter {draft.iteration.candidate_iter} rejected: score {assessment.previous_score} -> {decision.candidate_score}; reason={reason}",
        file=sys.stderr,
    )
    _outcome_dependency("apply_rejected_refinement_state", _apply_rejected_refinement_state)(
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
    _outcome_dependency("save_session", _save_session)(cwd, state)
    return RefinementIterationRun(
        result=_outcome_dependency("rejected_refinement_result", _rejected_refinement_result)(
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
