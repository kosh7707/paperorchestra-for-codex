from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.citation_gap_constants import TARGET_SUPPORT_STATUSES, V3_PASSTHROUGH_FIELDS
from paperorchestra.loop_engine.quality.citation_gap_v3_evidence import v3_case_gap_evidence


def v3_citation_support_gap_items(cases: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in (v3_case_gap_item(case) for case in cases or [])
        if isinstance(item, dict) and str(item.get("support_status") or "").strip() in TARGET_SUPPORT_STATUSES
    ]


def v3_case_gap_item(case: Any) -> dict[str, Any] | None:
    if not isinstance(case, dict):
        return None
    verdict = _v3_gap_verdict(case)
    support_status = _support_status_for_v3_verdict(verdict)
    if support_status is None:
        return None
    key = str(case.get("key") or "").strip()
    if not key:
        return None
    source = case.get("source") if isinstance(case.get("source"), dict) else {}
    item: dict[str, Any] = {
        "id": str(case.get("id") or f"case:{key}"),
        "case_id": str(case.get("id") or f"case:{key}"),
        "citation_keys": [key],
        "citation_entries": [{"key": key, "title": source.get("title"), "url": source.get("url")}],
        "support_status": support_status,
        "review_schema": "citation-support-review/3",
        "verdict": verdict,
        "evidence": v3_case_gap_evidence(case),
    }
    for field in V3_PASSTHROUGH_FIELDS:
        if field in case:
            item[field] = case[field]
    return item


def _v3_gap_verdict(case: dict[str, Any]) -> str:
    return str(case.get("verdict") or "human_needed").strip().lower() or "human_needed"


def _support_status_for_v3_verdict(verdict: str) -> str | None:
    if verdict == "human_needed":
        return "needs_manual_check"
    if verdict == "weak":
        return "weakly_supported"
    return None
