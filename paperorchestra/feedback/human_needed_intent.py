from __future__ import annotations

import re

from paperorchestra.core.errors import ContractError

HUMAN_NEEDED_DECISION_KINDS = {
    "approve_existing_candidate",
    "generate_new_operator_candidate",
    "reject_candidate_with_reason",
}


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
