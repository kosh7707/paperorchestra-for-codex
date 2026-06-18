from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.citation_gap_constants import TARGET_SUPPORT_STATUSES
from paperorchestra.loop_engine.quality.citation_gap_v3_evidence import (
    v3_case_evidence_entries as _v3_case_evidence_entries,
    v3_case_gap_evidence as _v3_case_gap_evidence,
)
from paperorchestra.loop_engine.quality.citation_gap_v3_items import (
    v3_case_gap_item as _v3_case_gap_item,
    v3_citation_support_gap_items,
)


def citation_support_gap_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    if payload.get("schema") == "citation-support-review/3":
        return v3_citation_support_gap_items(payload.get("cases")), True
    return legacy_citation_support_gap_items(payload.get("items")), False


def legacy_citation_support_gap_items(items: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in items or []
        if isinstance(item, dict) and str(item.get("support_status") or "").strip() in TARGET_SUPPORT_STATUSES
    ]


__all__ = [
    "TARGET_SUPPORT_STATUSES",
    "citation_support_gap_items",
    "legacy_citation_support_gap_items",
    "_v3_case_evidence_entries",
    "_v3_case_gap_evidence",
    "_v3_case_gap_item",
]
