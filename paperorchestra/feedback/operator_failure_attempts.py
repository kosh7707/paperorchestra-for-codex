from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_failure_progress import _compact_blocked_candidate_progress, _unique_strings


def _compact_operator_attempt_failure(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic, code-only diagnostics from the latest operator attempt."""

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
