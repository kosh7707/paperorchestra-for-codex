from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_text
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion_trace import _file_sha256
from paperorchestra.engine.refine_iteration_types import (
    PreparedRefinementDraft,
    RefinementCandidateAssessment,
    RefinementIterationRun,
    RefinementReviewDecision,
    RefinementValidationOutcome,
)
from paperorchestra.engine.refine_iteration_runs import (
    accepted_iteration_run_with_hooks,
    candidate_only_iteration_run_with_hooks,
    rejected_iteration_run_with_hooks,
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
    return candidate_only_iteration_run_with_hooks(
        cwd=cwd,
        iteration=iteration,
        assessment=assessment,
        contract_regression_preservation=contract_regression_preservation,
        load_session_fn=load_session,
        save_session_fn=save_session,
        apply_candidate_only_state_fn=apply_candidate_only_refinement_state,
        candidate_only_result_fn=candidate_only_result,
        file_sha256_fn=_file_sha256,
    )


def accepted_iteration_run(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
) -> RefinementIterationRun:
    return accepted_iteration_run_with_hooks(
        cwd=cwd,
        draft=draft,
        assessment=assessment,
        decision=decision,
        artifact_path_fn=artifact_path,
        write_text_fn=write_text,
        record_lane_manifest_fn=record_accepted_refinement_lane_manifest,
        load_session_fn=load_session,
        save_session_fn=save_session,
        apply_accepted_state_fn=apply_accepted_refinement_state,
        accepted_result_fn=accepted_refinement_result,
    )


def rejected_iteration_run(
    *,
    cwd: str | Path | None,
    draft: PreparedRefinementDraft,
    assessment: RefinementCandidateAssessment,
    decision: RefinementReviewDecision,
) -> RefinementIterationRun:
    return rejected_iteration_run_with_hooks(
        cwd=cwd,
        draft=draft,
        assessment=assessment,
        decision=decision,
        record_lane_manifest_fn=record_rejected_refinement_lane_manifest,
        load_session_fn=load_session,
        save_session_fn=save_session,
        apply_rejected_state_fn=apply_rejected_refinement_state,
        rejected_result_fn=rejected_refinement_result,
    )


__all__ = [
    "PreparedRefinementDraft",
    "RefinementCandidateAssessment",
    "RefinementIterationRun",
    "RefinementReviewDecision",
    "_blocking_issues",
    "_file_sha256",
    "_issue_messages",
    "_record_validation_report",
    "accepted_iteration_run",
    "accepted_refinement_result",
    "apply_accepted_refinement_state",
    "apply_candidate_only_refinement_state",
    "apply_rejected_refinement_state",
    "artifact_path",
    "candidate_only_iteration_run",
    "candidate_only_result",
    "contract_validation_failed_result",
    "load_session",
    "record_accepted_refinement_lane_manifest",
    "record_refinement_validation_outcome",
    "record_rejected_refinement_lane_manifest",
    "rejected_iteration_run",
    "rejected_refinement_result",
    "save_session",
    "write_text",
]
