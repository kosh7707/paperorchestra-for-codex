from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_answer_metadata import OPERATOR_FEEDBACK_INTENTS
from paperorchestra.feedback.operator_issue_constants import ACTIONABLE_FAILURE_OWNER_CATEGORIES, OPERATOR_SOURCE
from paperorchestra.feedback.operator_issue_identity import _normalize_issue_text, derive_operator_issue_id
from paperorchestra.feedback.operator_issue_owner import _owner_category_for_issue, _validated_owner_category

_REQUIRED_OPERATOR_ISSUE_FIELDS = (
    "id",
    "source_artifact_role",
    "source_item_key",
    "target_section",
    "severity",
    "rationale",
    "suggested_action",
    "authority_class",
)


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


def _validate_operator_issue(issue: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in _REQUIRED_OPERATOR_ISSUE_FIELDS if not str(issue.get(key) or "").strip()]
    if missing:
        raise ContractError(f"operator feedback issue is missing required fields: {', '.join(missing)}")
    _validate_issue_id(issue, packet)
    _validate_operator_provenance(issue)
    normalized = dict(issue)
    normalized["source"] = OPERATOR_SOURCE
    normalized["not_independent_human_review"] = True
    normalized["owner_category"] = _validated_owner_category(issue)
    return normalized


def _validate_issue_id(issue: dict[str, Any], packet: dict[str, Any]) -> None:
    expected_id = derive_operator_issue_id(
        str(packet["packet_sha256"]),
        source_artifact_role=str(issue["source_artifact_role"]),
        source_item_key=str(issue["source_item_key"]),
        target_section=str(issue["target_section"]),
        rationale=str(issue["rationale"]),
        suggested_action=str(issue["suggested_action"]),
    )
    if issue.get("id") != expected_id:
        raise ContractError(f"operator feedback issue id is not derivable from packet: {issue.get('id')}")


def _validate_operator_provenance(issue: dict[str, Any]) -> None:
    if issue.get("source") not in {None, OPERATOR_SOURCE}:
        raise ContractError("operator feedback issue source must be codex_operator")
    if issue.get("not_independent_human_review") not in {None, True}:
        raise ContractError("operator feedback issue must not claim independent human review")


def _action_for_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": f"operator-feedback:{issue['id']}",
        "code": "operator_feedback_issue",
        "automation": "semi_auto",
        "source_issue_id": issue["id"],
        "target_section": issue["target_section"],
        "authority_class": issue["authority_class"],
        "owner_category": issue["owner_category"],
        "reason": issue["rationale"],
        "suggested_action": issue["suggested_action"],
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
    }

__all__ = [
    "ACTIONABLE_FAILURE_OWNER_CATEGORIES",
    "OPERATOR_SOURCE",
    "_action_for_issue",
    "_normalize_issue_text",
    "_normalize_operator_intent",
    "_owner_category_for_issue",
    "_validate_operator_issue",
    "derive_operator_issue_id",
]
