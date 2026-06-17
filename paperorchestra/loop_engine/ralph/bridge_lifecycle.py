from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.loop_engine.quality.loop import append_quality_loop_history
from paperorchestra.loop_engine.ralph.artifacts import _write_execution_artifact
from paperorchestra.loop_engine.ralph.state import StepResult, _failing_codes, qa_loop_exit_code


def record_unsupported_actions(execution: dict[str, Any], unsupported_actions: list[dict[str, Any]]) -> None:
    for action in unsupported_actions:
        execution["actions_skipped"].append({"code": action.get("code"), "reason": "unsupported_handler"})


def finish_terminal_noop(cwd: str | Path | None, execution: dict[str, Any], verdict: str) -> StepResult:
    execution.update({"completed_at": utc_now_iso(), "verdict": verdict, "terminal_noop": True})
    path = _write_execution_artifact(cwd, execution)
    return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code(verdict))


def finish_no_supported_actions(cwd: str | Path | None, execution: dict[str, Any]) -> StepResult:
    execution.update(
        {
            "completed_at": utc_now_iso(),
            "verdict": "human_needed",
            "reason": "no_supported_executable_handlers",
        }
    )
    path = _write_execution_artifact(cwd, execution)
    return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code("human_needed"))


def finish_execution_error(
    *,
    cwd: str | Path | None,
    execution: dict[str, Any],
    before_eval: dict[str, Any],
    before_plan_path: str | Path,
    before_eval_path: str | Path,
    error: Exception,
    citation_candidate_applied: bool,
) -> StepResult:
    execution.update(
        {
            "completed_at": utc_now_iso(),
            "verdict": "execution_error",
            "error": str(error),
            "candidate_rollback": {"reason": "exception"} if citation_candidate_applied else None,
        }
    )
    path = _write_execution_artifact(cwd, execution)
    if execution["actions_attempted"]:
        append_quality_loop_history(
            cwd,
            before_eval,
            verdict="execution_error",
            plan_path=before_plan_path,
            quality_eval_path=before_eval_path,
            execution_path=path,
            event_type="qa_loop_step",
            consumes_budget=True,
        )
    return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code("execution_error"))


def finish_successful_step(
    *,
    cwd: str | Path | None,
    execution: dict[str, Any],
    final_eval: dict[str, Any],
    final_eval_path: str | Path,
    final_plan_path: str | Path,
    final_summary: dict[str, Any],
    final_progress: dict[str, Any],
    final_verification: dict[str, Any],
    verdict: str,
) -> StepResult:
    execution.update(
        {
            "completed_at": utc_now_iso(),
            "verification": final_verification,
            "after": {"failing_codes": _failing_codes(final_eval), "citation_support_summary": final_summary},
            "progress": final_progress,
            "verdict": verdict,
        }
    )
    path = _write_execution_artifact(cwd, execution)
    if execution["actions_attempted"]:
        append_quality_loop_history(
            cwd,
            final_eval,
            verdict=verdict,
            plan_path=final_plan_path,
            quality_eval_path=final_eval_path,
            execution_path=path,
            event_type="qa_loop_step",
            consumes_budget=True,
            extra={"actionable_failure": execution.get("actionable_failure")}
            if execution.get("actionable_failure")
            else None,
        )
    return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code(verdict))
