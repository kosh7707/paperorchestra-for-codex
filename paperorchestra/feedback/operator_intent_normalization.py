from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_answer_metadata import OPERATOR_FEEDBACK_INTENTS


def _normalize_operator_intent(feedback: dict[str, Any]) -> str:
    intents = _feedback_intents(feedback)
    primary = str(feedback.get("primary_intent") or "").strip()
    normalized = [intent for intent in dict.fromkeys(intents) if intent]
    invalid = [intent for intent in normalized + ([primary] if primary else []) if intent not in OPERATOR_FEEDBACK_INTENTS]
    if invalid:
        raise ContractError(f"unsupported operator feedback intent: {', '.join(invalid)}")
    if primary:
        if primary not in normalized and normalized:
            raise ContractError("operator feedback primary_intent must be included in intents")
        return primary
    if len(normalized) != 1:
        raise ContractError("operator feedback must include exactly one machine-readable intent or a primary_intent")
    return normalized[0]


def _feedback_intents(feedback: dict[str, Any]) -> list[str]:
    intents: list[str] = []
    raw_intents = feedback.get("intents")
    if isinstance(raw_intents, list):
        intents.extend(str(item) for item in raw_intents if str(item or "").strip())
    if str(feedback.get("intent") or "").strip():
        intents.append(str(feedback["intent"]))
    intents.extend(_action_kind_values(feedback.get("issues")))
    intents.extend(_action_kind_values(feedback.get("actions")))
    return intents


def _action_kind_values(items: Any) -> list[str]:
    return [
        str(item["action_kind"])
        for item in items or []
        if isinstance(item, dict) and str(item.get("action_kind") or "").strip()
    ]
