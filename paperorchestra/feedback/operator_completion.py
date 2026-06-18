from __future__ import annotations

from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.feedback.operator_failure_payload import _operator_actionable_failure
from paperorchestra.feedback.operator_records import _operator_feedback_verdict


def _operator_executor_crashed(execution: dict[str, Any]) -> bool:
    return any(
        str(attempt.get("executor_failure_category") or "none") != "none"
        for attempt in execution.get("attempts") or []
        if isinstance(attempt, dict)
    )


def _non_promoted_actionable_failure(
    *,
    promoted: bool,
    executor_crashed: bool,
    intent: str,
    execution: dict[str, Any],
    owner_categories: list[str],
) -> dict[str, Any] | None:
    if promoted:
        return None
    if executor_crashed:
        failure_reason = "supervised operator feedback command failed"
        failure_category = "operator_execution_error"
        failure_code = "operator_executor_crashed"
    elif intent == "reject_candidate_with_reason":
        failure_reason = "operator feedback explicitly rejected the candidate"
        failure_category = "operator_rejected_candidate"
        failure_code = "operator_rejected_candidate"
    else:
        failure_reason = "operator feedback did not produce an acceptable canonical manuscript update"
        failure_category = "operator_candidate_failed_hard_gate"
        failure_code = str(execution.get("promotion_reason") or "operator_candidate_failed_hard_gate")
    return _operator_actionable_failure(
        owner_categories,
        failure_reason,
        category=failure_category,
        code=failure_code,
        attempts=execution.get("attempts") or [],
    )


def _operator_final_execution_update(
    *,
    execution: dict[str, Any],
    promoted: bool,
    executor_crashed: bool,
    plan: dict[str, Any],
    max_supervised_iterations: int,
    after_sha: str,
    final_candidate_result: dict[str, Any] | None,
    incorporation_path: str,
    verification_block: dict[str, Any],
    actionable_failure: dict[str, Any] | None,
) -> dict[str, Any]:
    attempt_count = len(execution.get("attempts") or [])
    return {
        "completed_at": utc_now_iso(),
        "verdict": _operator_feedback_verdict(executor_crashed=executor_crashed, promoted=promoted, plan=plan),
        "supervised_iteration_index": attempt_count,
        "supervised_remaining": max(max_supervised_iterations - attempt_count, 0),
        "supervised_budget_exhausted": not promoted and attempt_count >= max_supervised_iterations,
        "manuscript_sha256_after": after_sha,
        "candidate_result": final_candidate_result,
        "incorporation_report": str(incorporation_path),
        "verification": verification_block,
        "actionable_failure": actionable_failure,
    }


def _operator_history_extra(
    execution: dict[str, Any],
    actionable_failure: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "supervised_iteration_index": execution.get("supervised_iteration_index"),
        "supervised_max_iterations": execution.get("supervised_max_iterations"),
        "supervised_remaining": execution.get("supervised_remaining"),
        "supervised_budget_exhausted": execution.get("supervised_budget_exhausted"),
        "promotion_status": execution.get("promotion_status"),
        "post_promotion_qa_verdict": execution.get("post_promotion_qa_verdict"),
        "actionable_failure": actionable_failure,
    }


def _operator_exception_actionable_failures(
    *,
    owner_categories: list[str],
    execution: dict[str, Any],
    exc: Exception,
) -> tuple[dict[str, Any], dict[str, Any]]:
    public_failure = _operator_actionable_failure(
        owner_categories,
        "supervised operator feedback command failed",
        category="operator_execution_error",
        code="supervised_operator_feedback_command_failed",
        attempts=execution.get("attempts") or [],
        execution_error=type(exc).__name__ + ": " + str(exc),
    )
    history_failure = _operator_actionable_failure(
        owner_categories,
        "supervised operator feedback command failed",
        category="operator_execution_error",
        code="supervised_operator_feedback_command_failed",
        attempts=execution.get("attempts") or [],
    )
    history_failure["error_type"] = type(exc).__name__
    return public_failure, history_failure


def _operator_exception_history_extra(
    execution: dict[str, Any],
    actionable_failure: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    attempt_count = len(execution.get("attempts") or []) or 1
    return {
        "supervised_iteration_index": attempt_count,
        "supervised_max_iterations": execution["supervised_max_iterations"],
        "supervised_remaining": max(execution["supervised_max_iterations"] - attempt_count, 0),
        "supervised_budget_exhausted": True,
        "execution_error_type": type(exc).__name__,
        "promotion_status": "rolled_back",
        "actionable_failure": actionable_failure,
    }


def _operator_exception_execution_update(
    *,
    exc: Exception,
    restored_block: dict[str, Any],
    actionable_failure: dict[str, Any],
) -> dict[str, Any]:
    return {
        "completed_at": utc_now_iso(),
        "verdict": "execution_error",
        "promotion_status": "rolled_back",
        "post_promotion_qa_verdict": None,
        "error": str(exc),
        "candidate_rollback": {"reason": "exception", "restored_verification": restored_block},
        "verification": {"restored_after_exception": restored_block},
        "actionable_failure": actionable_failure,
    }
