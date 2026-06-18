from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_quality_item_helpers import (
    _first_claim_id,
    _public_case_id,
    _public_failure_code,
    _public_failure_message,
    _quality_item_id,
    _sha256_text,
    _support_by_key,
    _support_groups_for_quality_items,
    _worst_support_status,
)
from paperorchestra.reviews.citation_quality_v3_items import _support_items_from_v3_cases, _v3_support_status


def _support_items(payload: Any, *, run_root: Path | None = None) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and payload.get("schema") == "citation-support-review/3":
        return _support_items_from_v3_cases(payload.get("cases"), run_root=run_root)
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


__all__ = [
    "_first_claim_id",
    "_public_case_id",
    "_public_failure_code",
    "_public_failure_message",
    "_quality_item_id",
    "_sha256_text",
    "_support_by_key",
    "_support_groups_for_quality_items",
    "_support_items",
    "_support_items_from_v3_cases",
    "_v3_support_status",
    "_worst_support_status",
]
