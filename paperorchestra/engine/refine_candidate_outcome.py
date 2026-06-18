from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session as _load_session, save_session as _save_session
from paperorchestra.engine.completion import _file_sha256 as _file_sha256_real
from paperorchestra.engine.refine_iteration_outcome_dependencies import _outcome_dependency
from paperorchestra.engine.refine_iteration_types import RefinementCandidateAssessment, RefinementIterationRun
from paperorchestra.engine.refine_persistence import apply_candidate_only_refinement_state as _apply_candidate_only_refinement_state
from paperorchestra.engine.refine_results import candidate_only_result as _candidate_only_result


def candidate_only_iteration_run(
    *,
    cwd: str | Path | None,
    iteration: Any,
    assessment: RefinementCandidateAssessment,
    contract_regression_preservation: Any,
) -> RefinementIterationRun:
    state = _outcome_dependency("load_session", _load_session)(cwd)
    _outcome_dependency("apply_candidate_only_refinement_state", _apply_candidate_only_refinement_state)(
        state,
        temp_state_paper=assessment.temp_state_paper,
        temp_latest_review=assessment.temp_latest_review,
        validation_path=assessment.validation_path,
        temp_review_history_len=assessment.temp_review_history_len,
    )
    _outcome_dependency("save_session", _save_session)(cwd, state)
    return RefinementIterationRun(
        result=_outcome_dependency("candidate_only_result", _candidate_only_result)(
            iteration=iteration.candidate_iter,
            score_before=assessment.previous_score,
            score_after=assessment.candidate_score,
            axis_scores_before=assessment.previous_axes,
            axis_scores_after=assessment.candidate_axes,
            paper_path=assessment.temp_state_paper,
            candidate_path=assessment.candidate_tex_path,
            candidate_sha256=_outcome_dependency("_file_sha256", _file_sha256_real)(assessment.candidate_tex_path),
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
