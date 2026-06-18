from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.feedback import human_needed_records as _records
from paperorchestra.feedback.packet_records import _artifact_by_role

HUMAN_NEEDED_DECISION_KINDS = {
    "approve_existing_candidate",
    "generate_new_operator_candidate",
    "reject_candidate_with_reason",
}

_REJECT_TOKENS = (
    "reject",
    "do not",
    "don't",
    "rollback",
    "거절",
    "반려",
    "하지마",
    "하지 마",
    "승인하지",
    "approve하지",
)

_APPROVAL_PATTERNS = (
    r"\bapprove_existing_candidate\b",
    r"\bapprove\s+(?:the\s+)?(?:existing\s+|ready\s+)?candidate\b",
    r"\bpromote\s+(?:the\s+)?(?:existing\s+|ready\s+)?candidate\b",
    r"\baccept\s+(?:the\s+)?(?:existing\s+|ready\s+)?candidate\b",
    r"후보(?:를)?\s*승인",
    r"후보(?:를)?\s*채택",
    r"candidate(?:를)?\s*승인",
)


def _load_artifact_payload(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _human_needed_actions(packet: dict[str, Any]) -> list[dict[str, Any]]:
    plan = _load_artifact_payload(packet, "qa_loop_plan")
    if not isinstance(plan, dict):
        return []
    return [
        action
        for action in plan.get("repair_actions") or []
        if isinstance(action, dict) and str(action.get("automation") or "") == "human_needed"
    ]


def _select_action(actions: list[dict[str, Any]], action_id: str | None, *, candidate_role: str | None) -> dict[str, Any] | None:
    if action_id:
        matches = [action for action in actions if _records._action_id(action) == action_id]
        if len(matches) != 1:
            raise ContractError(f"human_needed action_id not found or ambiguous: {action_id}")
        return matches[0]
    if len(actions) > 1 and not candidate_role:
        raise ContractError("multiple human_needed actions require --action-id")
    if len(actions) == 1:
        return actions[0]
    return None


def _classify_action(action: dict[str, Any] | None, *, candidate_role: str | None = None) -> str:
    if candidate_role:
        return "candidate_approval"
    text = _action_text(action)
    if _has_any(text, ("citation", "reference", "bibliography", "claim")):
        return "citation_author_judgment"
    if _has_any(text, ("figure", "plot", "caption", "asset")):
        return "figure_grounding_decision"
    if _has_any(text, ("environment", "dependency", "compile", "sandbox")):
        return "environment_dependency"
    if "reviewer" in text or "independent" in text:
        return "reviewer_independence"
    if _has_any(text, ("no_progress", "budget", "retry", "stuck")):
        return "no_progress_escalation"
    if _records._action_id(action) or (action or {}).get("code"):
        return "general_operator_feedback"
    return "unsupported_handler"


def _action_text(action: dict[str, Any] | None) -> str:
    return " ".join(
        str((action or {}).get(key) or "")
        for key in ("id", "action_id", "code", "target", "reason", "suggested_action")
    ).lower()


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _resolve_decision_kind(answer: str, intent: str | None, *, candidate_role: str | None) -> str:
    if _explicit_reject(answer):
        return "reject_candidate_with_reason"
    if intent:
        if intent not in HUMAN_NEEDED_DECISION_KINDS:
            raise ContractError(f"unsupported human_needed intent: {intent}")
        if intent == "approve_existing_candidate" and not candidate_role:
            raise ContractError("approve_existing_candidate requires an actionable candidate approval artifact")
        return intent
    if candidate_role and _explicit_approve(answer):
        return "approve_existing_candidate"
    return "generate_new_operator_candidate"


def _explicit_reject(answer: str) -> bool:
    lowered = answer.lower()
    return any(token in lowered for token in _REJECT_TOKENS)


def _explicit_approve(answer: str) -> bool:
    lowered = answer.lower()
    # Candidate promotion is stronger than "continue"; broad proceed tokens
    # should generate a new bounded candidate unless intent is explicit.
    return any(re.search(pattern, lowered) for pattern in _APPROVAL_PATTERNS)


__all__ = [
    "HUMAN_NEEDED_DECISION_KINDS",
    "_classify_action",
    "_explicit_approve",
    "_explicit_reject",
    "_human_needed_actions",
    "_load_artifact_payload",
    "_resolve_decision_kind",
    "_select_action",
]
