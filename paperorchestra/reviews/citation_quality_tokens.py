from __future__ import annotations

import hashlib
from typing import Any


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    return {str(value).strip().lower()} if str(value).strip() else set()


def _tokens_for_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for field in fields:
        result.update(_tokens(payload.get(field)))
    return result


def _first_claim_id(claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        claim_id = claim.get("id") or claim.get("claim_id")
        if claim_id:
            return str(claim_id)
    return None


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
