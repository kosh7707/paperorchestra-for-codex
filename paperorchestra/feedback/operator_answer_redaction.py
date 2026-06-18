from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_answer_constants import HUMAN_NEEDED_METADATA_FORBIDDEN_KEYS


def _contains_forbidden_human_needed_metadata(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in HUMAN_NEEDED_METADATA_FORBIDDEN_KEYS:
                return True
            if str(key) == "answer" and str(value) != "redacted":
                return True
            if _contains_forbidden_human_needed_metadata(value):
                return True
    if isinstance(payload, list):
        return any(_contains_forbidden_human_needed_metadata(item) for item in payload)
    return False


def validate_operator_review_notes(notes: Any) -> dict[str, Any]:
    if not isinstance(notes, dict):
        raise ContractError("operator_review_notes must be a JSON object")
    if _contains_forbidden_human_needed_metadata(notes):
        raise ContractError("operator_review_notes must not contain raw/private answer data")
    return dict(notes)
