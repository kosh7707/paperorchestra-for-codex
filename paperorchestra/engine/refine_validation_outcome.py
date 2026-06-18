from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from paperorchestra.core.session import save_session
from paperorchestra.engine.refine_iteration_types import RefinementIterationRun, RefinementValidationOutcome
from paperorchestra.engine.refine_results import contract_validation_failed_result
from paperorchestra.engine.reports import _blocking_issues, _issue_messages, _record_validation_report


def _outcome_dependency(name: str, default: Callable[..., Any]) -> Callable[..., Any]:
    outcomes = sys.modules.get("paperorchestra.engine.refine_iteration_outcomes")
    if outcomes is None:
        return default
    return getattr(outcomes, name, default)


def record_refinement_validation_outcome(
    *,
    cwd: str | Path | None,
    state: Any,
    iteration: Any,
    validation_issues: list[Any],
    validation_name: str,
    latex: str,
) -> RefinementValidationOutcome:
    issue_messages = _outcome_dependency("_issue_messages", _issue_messages)
    validation_path, validation_payload = _outcome_dependency("_record_validation_report", _record_validation_report)(
        cwd,
        stage="refinement",
        issues=validation_issues,
        name=validation_name,
        manuscript_text=latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _outcome_dependency("_blocking_issues", _blocking_issues)(validation_issues)
    if not blocking_issues:
        if validation_issues:
            state.notes.append(
                f"Refinement iteration {state.refinement_iteration + 1} produced validation warnings: "
                + " | ".join(issue_messages(validation_issues))
            )
        return RefinementValidationOutcome(
            validation_path=validation_path,
            validation_payload=validation_payload,
            failure_run=None,
        )

    result = _outcome_dependency("contract_validation_failed_result", contract_validation_failed_result)(
        iteration=state.refinement_iteration + 1,
        score_before=state.review_history[-1].overall_score
        if state.review_history
        else float(iteration.review_payload.get("overall_score", 0.0)),
        paper_path=state.artifacts.paper_full_tex,
        issues=issue_messages(blocking_issues),
        validation_path=validation_path,
        validation_payload=validation_payload,
    )
    state.notes.append(f"Rejected refinement iteration {state.refinement_iteration + 1} due to contract validation failure.")
    print(
        f"Refinement iter {state.refinement_iteration + 1} rejected: contract validation failed ({'; '.join(issue_messages(blocking_issues))})",
        file=sys.stderr,
    )
    _outcome_dependency("save_session", save_session)(cwd, state)
    return RefinementValidationOutcome(
        validation_path=validation_path,
        validation_payload=validation_payload,
        failure_run=RefinementIterationRun(result=result, stop_after=True),
    )
