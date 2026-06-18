from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_quality_item_public import (
    _first_claim_id,
    _public_case_id,
    _public_failure_code,
    _public_failure_message,
    _quality_item_id,
    _sha256_text,
    _support_groups_for_quality_items,
)


def _support_by_key(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for key in item.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(item)
    return result


def _worst_support_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "unknown"
    order = ["contradicted", "unsupported", "metadata_only", "insufficient_evidence", "unknown", "supported"]
    statuses = {str(item.get("support_status") or "unknown").strip().lower() or "unknown" for item in items}
    for status in order:
        if status in statuses:
            return status
    return sorted(statuses)[0]

__all__ = [
    "_first_claim_id",
    "_public_case_id",
    "_public_failure_code",
    "_public_failure_message",
    "_quality_item_id",
    "_sha256_text",
    "_support_by_key",
    "_support_groups_for_quality_items",
    "_worst_support_status",
]
