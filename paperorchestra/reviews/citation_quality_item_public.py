from __future__ import annotations

import hashlib
from typing import Any

from paperorchestra.reviews.citation_quality_public import _default_public_failure_message


def _public_case_id(support_items: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str | None:
    for item in support_items:
        case_id = item.get("case_id") or item.get("id")
        if case_id:
            return str(case_id)
    return _first_claim_id(claims)


def _support_groups_for_quality_items(support_items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not support_items:
        return [[]]
    v3_items = [item for item in support_items if item.get("review_schema") == "citation-support-review/3"]
    if not v3_items:
        return [support_items]
    groups = [[item] for item in v3_items]
    legacy_items = [item for item in support_items if item.get("review_schema") != "citation-support-review/3"]
    if legacy_items:
        groups.append(legacy_items)
    return groups


def _quality_item_id(key: str, support_items: list[dict[str, Any]], *, group_index: int) -> str:
    for item in support_items:
        if item.get("review_schema") == "citation-support-review/3":
            case_id = str(item.get("case_id") or item.get("id") or "").strip()
            basis = f"{key}:v3:{case_id}:{group_index}"
            return f"redacted-citation-item:{_sha256_text(basis)[:12]}"
    return f"redacted-citation-item:{_sha256_text(key)[:12]}"


def _public_failure_code(support_items: list[dict[str, Any]], key_failures: list[str]) -> str | None:
    for item in support_items:
        if item.get("review_schema") == "citation-support-review/3" and item.get("verdict") == "human_needed":
            return "human_needed"
    return str(key_failures[0]) if key_failures else None


def _public_failure_message(support_items: list[dict[str, Any]], key_failures: list[str]) -> str | None:
    code = _public_failure_code(support_items, key_failures)
    return _default_public_failure_message(code) if code else None


def _first_claim_id(claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        claim_id = claim.get("id") or claim.get("claim_id")
        if claim_id:
            return str(claim_id)
    return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
