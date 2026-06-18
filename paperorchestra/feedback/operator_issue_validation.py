from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_issue_constants import OPERATOR_SOURCE
from paperorchestra.feedback.operator_issue_identity import derive_operator_issue_id
from paperorchestra.feedback.operator_issue_owner import _validated_owner_category


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
