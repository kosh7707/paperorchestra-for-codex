from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import write_text as _write_text
from paperorchestra.core.session import artifact_path as _artifact_path, load_session as _load_session, save_session as _save_session
from paperorchestra.engine.refine_iteration_outcome_dependencies import _outcome_dependency
from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
)
from paperorchestra.engine.refine_manifests import record_accepted_refinement_lane_manifest as _record_accepted_refinement_lane_manifest
from paperorchestra.engine.refine_persistence import apply_accepted_refinement_state as _apply_accepted_refinement_state
from paperorchestra.engine.refine_results import accepted_refinement_result as _accepted_refinement_result


def accepted_iteration_run(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
) -> RefinementIterationRun:
    final_path = _outcome_dependency("artifact_path", _artifact_path)(cwd, "paper.full.tex")
    _outcome_dependency("write_text", _write_text)(final_path, assessment.latex)
    lane_path = _outcome_dependency(
        "record_accepted_refinement_lane_manifest",
        _record_accepted_refinement_lane_manifest,
    )(
        cwd,
        runtime_mode=draft.runtime_mode,
        lane_type=draft.lane_type,
        fallback_used=draft.fallback_used,
        input_artifacts=[assessment.temp_state_paper, assessment.temp_latest_review or ""],
        output_artifacts=[str(final_path), str(assessment.worklog_path), str(assessment.validation_path)],
        notes=assessment.lane_notes,
    )
    state = _outcome_dependency("load_session", _load_session)(cwd)
    _outcome_dependency("apply_accepted_refinement_state", _apply_accepted_refinement_state)(
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
    _outcome_dependency("save_session", _save_session)(cwd, state)
    return RefinementIterationRun(
        result=_outcome_dependency("accepted_refinement_result", _accepted_refinement_result)(
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
