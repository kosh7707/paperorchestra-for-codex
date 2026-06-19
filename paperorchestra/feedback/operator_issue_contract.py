from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_issue_identity import _normalize_issue_text, derive_operator_issue_id
from paperorchestra.feedback.operator_issue_intent import _action_kind_values, _feedback_intents, _normalize_operator_intent

OPERATOR_SOURCE = "codex_operator"

ACTIONABLE_FAILURE_OWNER_CATEGORIES = {
    "author",
    "evidence",
    "experiment",
    "layout",
    "proof",
    "bibliography",
    "implementation",
    "execution_error",
}

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


def _owner_category_for_issue(issue: dict[str, Any]) -> str:
    text = " ".join(
        str(issue.get(key) or "")
        for key in ("target_section", "rationale", "suggested_action", "authority_class")
    ).lower()
    if any(token in text for token in ("experiment", "benchmark", "evaluation", "result")):
        return "experiment"
    if any(token in text for token in ("proof", "theorem", "security", "bound")):
        return "proof"
    if any(token in text for token in ("citation", "bibliography", "reference", "bibtex")):
        return "bibliography"
    if any(token in text for token in ("compile", "validation", "implementation", "execution")):
        return "implementation"
    return "author"


def _validated_owner_category(issue: dict[str, Any]) -> str:
    owner_category = str(issue.get("owner_category") or _owner_category_for_issue(issue))
    if owner_category not in ACTIONABLE_FAILURE_OWNER_CATEGORIES:
        raise ContractError(f"invalid owner_category for operator issue: {owner_category}")
    return owner_category


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
