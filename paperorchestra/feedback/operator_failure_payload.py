from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_failure_attempts import _compact_operator_attempt_failure
from paperorchestra.feedback.operator_failure_base import _actionable_failure

_OPERATOR_FAILURE_NEXT_STEPS = [
    "Inspect latest_gate_reasons before retrying operator feedback.",
    "Address new Tier 2 failures before promoting a candidate.",
    "Avoid identical or no-progress candidates; rerun the QA loop after targeted changes.",
]


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
