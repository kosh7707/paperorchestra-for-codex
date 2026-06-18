from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.policy import BUDGET_CONSUMING_HISTORY_EVENTS


def _history_entry_consumes_budget(entry: dict[str, Any]) -> bool:
    if "consumes_budget" in entry:
        return bool(entry.get("consumes_budget"))
    return str(entry.get("event_type") or "") in BUDGET_CONSUMING_HISTORY_EVENTS


def _actionable_failure_signature(entry: dict[str, Any]) -> dict[str, Any] | None:
    failure = entry.get("actionable_failure")
    if not isinstance(failure, dict):
        return None
    category = str(failure.get("category") or "").strip()
    code = str(failure.get("code") or "").strip()
    reason = str(failure.get("reason") or "").strip()
    validation_codes = sorted(
        {str(code).strip() for code in failure.get("validation_failing_codes") or [] if str(code).strip()}
    )
    if not any([category, code, reason, validation_codes]):
        return None
    return {
        "category": category,
        "code": code,
        "reason": reason,
        "validation_failing_codes": validation_codes,
    }


def _repeated_actionable_failure(budget_history: list[dict[str, Any]]) -> dict[str, Any]:
    signatures = [_actionable_failure_signature(entry) for entry in budget_history]
    signatures = [signature for signature in signatures if signature]
    if len(signatures) < 2:
        return {"detected": False, "count": len(signatures), "signature": signatures[-1] if signatures else None}
    latest = signatures[-1]
    count = 1
    for signature in reversed(signatures[:-1]):
        if signature != latest:
            break
        count += 1
    return {"detected": count >= 2, "count": count, "signature": latest}
