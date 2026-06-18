from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_failure_progress import _compact_blocked_candidate_progress, _unique_strings


def _compact_operator_attempt_failure(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    latest = attempts[-1] if attempts else {}
    if not isinstance(latest, dict):
        latest = {}
    payload: dict[str, Any] = {
        "attempt_index": latest.get("attempt_index"),
        "latest_gate_reasons": _unique_strings(latest.get("gate_reasons")),
        "new_tier2_failures": _unique_strings(latest.get("new_tier2_failures")),
        "resolved_active_failures": _unique_strings(latest.get("resolved_active_failures")),
        "candidate_active_failures": _unique_strings(latest.get("candidate_active_failures")),
        "base_active_failures": _unique_strings(latest.get("base_active_failures")),
    }
    executor_failure = str(latest.get("executor_failure_category") or "").strip()
    if executor_failure:
        payload["executor_failure_category"] = executor_failure
    blocked_progress = _compact_blocked_candidate_progress(latest)
    if blocked_progress:
        payload["blocked_candidate_progress"] = blocked_progress
    return payload


_OPERATOR_FAILURE_NEXT_STEPS = [
    "Inspect latest_gate_reasons before retrying operator feedback.",
    "Address new Tier 2 failures before promoting a candidate.",
    "Avoid identical or no-progress candidates; rerun the QA loop after targeted changes.",
]


def _actionable_failure(owner_categories: list[str], reason: str, *, execution_error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reason": reason,
        "owner_categories": sorted(dict.fromkeys(owner_categories or ["author"])),
    }
    if execution_error:
        payload["execution_error"] = execution_error
    return payload


def _operator_actionable_failure(
    owner_categories: list[str],
    reason: str,
    *,
    category: str,
    code: str,
    attempts: list[dict[str, Any]] | None = None,
    execution_error: str | None = None,
) -> dict[str, Any]:
    payload = _actionable_failure(owner_categories, reason, execution_error=execution_error)
    payload.update(
        {
            "category": category,
            "code": code,
            "next_steps": list(_OPERATOR_FAILURE_NEXT_STEPS),
        }
    )
    payload.update(_compact_operator_attempt_failure(attempts or []))
    return payload
