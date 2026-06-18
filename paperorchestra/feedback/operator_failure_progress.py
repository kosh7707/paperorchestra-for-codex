from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contexts.metrics import _compact_metric_delta_records


def _compact_blocked_candidate_progress(attempt: dict[str, Any]) -> dict[str, Any] | None:
    """Return safe diagnostics for candidates that improved but could not promote."""

    if not isinstance(attempt, dict) or attempt.get("gate_passed") is True:
        return None
    metric_delta = attempt.get("active_tier2_metric_delta")
    if not isinstance(metric_delta, dict):
        metric_delta = {}
    improvements = _compact_metric_delta_records(metric_delta.get("improvements"))
    regressions = _compact_metric_delta_records(metric_delta.get("regressions"))
    resolved = _unique_strings(attempt.get("resolved_active_failures"))
    gate_reasons = _unique_strings(attempt.get("gate_reasons"))
    new_tier2 = _unique_strings(attempt.get("new_tier2_failures"))
    total_improved = metric_delta.get("total_improved") is True
    if not (improvements or resolved or total_improved):
        return None
    payload: dict[str, Any] = {
        "kind": "active_metric_improved_but_blocked",
        "blocking_gate_reasons": gate_reasons,
        "new_tier2_failures": new_tier2,
        "resolved_active_failures": resolved,
        "metric_improvements": improvements,
        "metric_regressions": regressions,
        "base_total": _int_or_none(metric_delta.get("base_total")),
        "candidate_total": _int_or_none(metric_delta.get("candidate_total")),
        "total_improved": total_improved,
    }
    if new_tier2:
        payload["recommended_next_focus"] = new_tier2
    return payload


def _unique_strings(values: Any) -> list[str]:
    return sorted(dict.fromkeys(str(value) for value in values or [] if str(value).strip()))


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None
