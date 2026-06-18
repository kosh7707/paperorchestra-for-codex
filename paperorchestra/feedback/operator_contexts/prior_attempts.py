from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.metric_delta import _compact_metric_delta_records


def _compact_prior_rejected_attempts(
    attempts: list[dict[str, Any]] | None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return bounded code/count/hash-only memory for failed operator candidates."""

    result: list[dict[str, Any]] = []
    for attempt in attempts or []:
        if not isinstance(attempt, dict) or attempt.get("gate_passed") is True:
            continue
        compact = _compact_rejected_attempt(attempt)
        if compact:
            result.append(compact)
    return result[-limit:]


def _compact_rejected_attempt(attempt: dict[str, Any]) -> dict[str, Any] | None:
    gate_reasons = _unique_strings(attempt.get("gate_reasons"))
    if not gate_reasons:
        return None
    metric_delta = (
        attempt.get("active_tier2_metric_delta")
        if isinstance(attempt.get("active_tier2_metric_delta"), dict)
        else {}
    )
    compact: dict[str, Any] = {
        "attempt_index": attempt.get("attempt_index"),
        "candidate_sha256": str(attempt.get("candidate_sha256") or ""),
        "gate_reasons": gate_reasons,
        "resolved_active_failures": _unique_strings(attempt.get("resolved_active_failures")),
        "new_tier2_failures": _unique_strings(attempt.get("new_tier2_failures")),
        "candidate_active_failures": _unique_strings(attempt.get("candidate_active_failures")),
        "base_active_failures": _unique_strings(attempt.get("base_active_failures")),
    }
    if isinstance(metric_delta, dict):
        compact["metric_regressions"] = _compact_metric_delta_records(metric_delta.get("regressions"))
        compact["metric_improvements"] = _compact_metric_delta_records(metric_delta.get("improvements"))
        compact["base_total"] = metric_delta.get("base_total")
        compact["candidate_total"] = metric_delta.get("candidate_total")
    return compact


def _unique_strings(values: Any) -> list[str]:
    return sorted(dict.fromkeys(str(value) for value in values or [] if str(value).strip()))
