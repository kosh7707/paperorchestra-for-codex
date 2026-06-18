from __future__ import annotations

from typing import Any

TARGET_SUPPORT_STATUSES = {"needs_manual_check", "manual_check", "weakly_supported"}


def citation_support_gap_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    if payload.get("schema") == "citation-support-review/3":
        items = [
            item
            for item in (_v3_case_gap_item(case) for case in payload.get("cases") or [])
            if isinstance(item, dict) and str(item.get("support_status") or "").strip() in TARGET_SUPPORT_STATUSES
        ]
        return items, True
    items = [
        item
        for item in payload.get("items") or []
        if isinstance(item, dict) and str(item.get("support_status") or "").strip() in TARGET_SUPPORT_STATUSES
    ]
    return items, False


def _v3_case_gap_item(case: Any) -> dict[str, Any] | None:
    if not isinstance(case, dict):
        return None
    verdict = str(case.get("verdict") or "human_needed").strip().lower() or "human_needed"
    if verdict == "human_needed":
        support_status = "needs_manual_check"
    elif verdict == "weak":
        support_status = "weakly_supported"
    else:
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
        "evidence": _v3_case_gap_evidence(case),
    }
    for field in [
        "suggested_fix",
        "suggested_action",
        "requires_author_judgment",
        "author_judgment_required",
        "requires_operator_judgment",
        "operator_judgment_required",
        "authority_class",
        "flags",
    ]:
        if field in case:
            item[field] = case[field]
    return item


def _v3_case_gap_evidence(case: dict[str, Any]) -> list[dict[str, Any]]:
    key = str(case.get("key") or "").strip()
    evidence: list[dict[str, Any]] = []
    for field in ("support_evidence", "verified_support_evidence"):
        evidence.extend(_v3_case_evidence_entries(case.get(field), key=key, verified=True))
    resolution = case.get("resolution") if isinstance(case.get("resolution"), dict) else {}
    evidence.extend(_v3_case_evidence_entries(resolution.get("support_evidence"), key=key, verified=True))
    for field in ("evidence_surfaces", "evidence_candidates"):
        evidence.extend(_v3_case_evidence_entries(case.get(field), key=key, verified=False))
    return evidence


def _v3_case_evidence_entries(value: Any, *, key: str, verified: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        supports_claim = entry.get("supports_claim") if entry.get("supports_claim") is not None else entry.get("supports")
        entries.append(
            {
                "citation_key": entry.get("citation_key") or key,
                "source_title": entry.get("source_title") or entry.get("title"),
                "url": entry.get("url") or entry.get("source_url"),
                "evidence_quote_or_summary": entry.get("evidence_quote_or_summary")
                or entry.get("quoted_or_paraphrased_support")
                or entry.get("quote_or_summary")
                or entry.get("summary"),
                "supports_claim": supports_claim if verified else False,
            }
        )
    return entries
