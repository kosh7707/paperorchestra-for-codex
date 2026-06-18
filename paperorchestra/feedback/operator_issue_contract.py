from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_answer_metadata import OPERATOR_FEEDBACK_INTENTS
from paperorchestra.feedback.packet_artifacts import _canonical_sha256, _sha256_bytes

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


def _normalize_issue_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def derive_operator_issue_id(
    packet_sha256: str,
    *,
    source_artifact_role: str,
    source_item_key: str,
    target_section: str,
    rationale: str,
    suggested_action: str,
) -> str:
    issue_text = _normalize_issue_text(f"{rationale}\n{suggested_action}")
    issue_text_hash = _sha256_bytes(issue_text.encode("utf-8"))
    payload = {
        "packet_sha256": packet_sha256,
        "source_artifact_role": source_artifact_role,
        "source_item_key": source_item_key,
        "target_section": target_section,
        "issue_text_sha256": issue_text_hash,
    }
    return "opfb-" + _canonical_sha256(payload)[:20]


def _validate_operator_issue(issue: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    required = [
        "id",
        "source_artifact_role",
        "source_item_key",
        "target_section",
        "severity",
        "rationale",
        "suggested_action",
        "authority_class",
    ]
    missing = [key for key in required if not str(issue.get(key) or "").strip()]
    if missing:
        raise ContractError(f"operator feedback issue is missing required fields: {', '.join(missing)}")
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
    if issue.get("source") not in {None, OPERATOR_SOURCE}:
        raise ContractError("operator feedback issue source must be codex_operator")
    if issue.get("not_independent_human_review") not in {None, True}:
        raise ContractError("operator feedback issue must not claim independent human review")
    owner_category = str(issue.get("owner_category") or _owner_category_for_issue(issue))
    if owner_category not in ACTIONABLE_FAILURE_OWNER_CATEGORIES:
        raise ContractError(f"invalid owner_category for operator issue: {owner_category}")
    normalized = dict(issue)
    normalized["source"] = OPERATOR_SOURCE
    normalized["not_independent_human_review"] = True
    normalized["owner_category"] = owner_category
    return normalized


def _owner_category_for_issue(issue: dict[str, Any]) -> str:
    text = " ".join(str(issue.get(key) or "") for key in ("target_section", "rationale", "suggested_action", "authority_class")).lower()
    if any(token in text for token in ("experiment", "benchmark", "evaluation", "result")):
        return "experiment"
    if any(token in text for token in ("proof", "theorem", "security", "bound")):
        return "proof"
    if any(token in text for token in ("citation", "bibliography", "reference", "bibtex")):
        return "bibliography"
    if any(token in text for token in ("compile", "validation", "implementation", "execution")):
        return "implementation"
    return "author"


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


def _normalize_operator_intent(feedback: dict[str, Any]) -> str:
    intents: list[str] = []
    raw_intents = feedback.get("intents")
    if isinstance(raw_intents, list):
        intents.extend(str(item) for item in raw_intents if str(item or "").strip())
    if str(feedback.get("intent") or "").strip():
        intents.append(str(feedback["intent"]))
    for issue in feedback.get("issues") or []:
        if isinstance(issue, dict) and str(issue.get("action_kind") or "").strip():
            intents.append(str(issue["action_kind"]))
    for action in feedback.get("actions") or []:
        if isinstance(action, dict) and str(action.get("action_kind") or "").strip():
            intents.append(str(action["action_kind"]))
    primary = str(feedback.get("primary_intent") or "").strip()
    normalized = [intent for intent in dict.fromkeys(intents) if intent]
    invalid = [intent for intent in normalized + ([primary] if primary else []) if intent and intent not in OPERATOR_FEEDBACK_INTENTS]
    if invalid:
        raise ContractError(f"unsupported operator feedback intent: {', '.join(invalid)}")
    if primary:
        if primary not in normalized and normalized:
            raise ContractError("operator feedback primary_intent must be included in intents")
        return primary
    if len(normalized) != 1:
        raise ContractError("operator feedback must include exactly one machine-readable intent or a primary_intent")
    return normalized[0]
