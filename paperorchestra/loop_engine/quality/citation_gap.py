from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.critics import citation_item_has_valid_supporting_evidence
from .utils import _read_json_if_exists


AUTHOR_JUDGMENT_AUTHORITY_CLASSES = {"author_judgment", "operator_judgment", "domain_judgment", "author_feedback"}


def _citation_support_gap_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    target_statuses = {"needs_manual_check", "manual_check", "weakly_supported"}
    if payload.get("schema") == "citation-support-review/3":
        items = [
            item
            for item in (_v3_case_gap_item(case) for case in payload.get("cases") or [])
            if isinstance(item, dict) and str(item.get("support_status") or "").strip() in target_statuses
        ]
        return items, True
    items = [
        item
        for item in payload.get("items") or []
        if isinstance(item, dict) and str(item.get("support_status") or "").strip() in target_statuses
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
        normalized = {
            "citation_key": entry.get("citation_key") or key,
            "source_title": entry.get("source_title") or entry.get("title"),
            "url": entry.get("url") or entry.get("source_url"),
            "evidence_quote_or_summary": entry.get("evidence_quote_or_summary")
            or entry.get("quoted_or_paraphrased_support")
            or entry.get("quote_or_summary")
            or entry.get("summary"),
            "supports_claim": supports_claim if verified else False,
        }
        entries.append(normalized)
    return entries


def _citation_support_gap_classification(citation_check: dict[str, Any]) -> dict[str, Any]:
    path = citation_check.get("path")
    payload = _read_json_if_exists(path) if isinstance(path, (str, Path)) else None
    if not isinstance(payload, dict):
        return {
            "machine_solvable_count": 0,
            "machine_research_needed_count": 0,
            "manual_author_judgment_count": 1,
            "author_judgment_count": 1,
            "payload_unavailable": True,
        }
    manual_statuses = {"needs_manual_check", "manual_check"}
    items, v3_payload = _citation_support_gap_items(payload)
    if not items:
        return {
            "machine_solvable_count": 0,
            "machine_research_needed_count": 0,
            "manual_author_judgment_count": 0 if v3_payload else 1,
            "author_judgment_count": 0 if v3_payload else 1,
            "payload_unavailable": not v3_payload,
        }
    machine_solvable_count = 0
    machine_research_needed_count = 0
    manual_author_judgment_count = 0
    weak_author_marker_count = 0
    for item in items:
        status = str(item.get("support_status") or "").strip()
        suggested_fix = str(item.get("suggested_fix") or item.get("suggested_action") or "").strip()
        authority_class = str(item.get("authority_class") or "").strip().lower()
        flags = {str(flag).strip().lower() for flag in item.get("flags") or [] if str(flag).strip()} if isinstance(item.get("flags"), list) else set()
        explicit_author_judgment = (
            item.get("requires_author_judgment") is True
            or item.get("author_judgment_required") is True
            or item.get("requires_operator_judgment") is True
            or item.get("operator_judgment_required") is True
            or authority_class in AUTHOR_JUDGMENT_AUTHORITY_CLASSES
            or bool(
                flags
                & {
                    "requires_author_judgment",
                    "author_judgment_required",
                    "requires_operator_judgment",
                    "operator_judgment_required",
                    "operator_judgment",
                    "domain_judgment",
                    "author_feedback",
                }
            )
        )
        valid_support_evidence = citation_item_has_valid_supporting_evidence(item)
        evidence_surface = _has_concrete_unbound_evidence_surface(item)
        if suggested_fix and valid_support_evidence and not explicit_author_judgment:
            machine_solvable_count += 1
        elif suggested_fix and evidence_surface and not explicit_author_judgment:
            machine_research_needed_count += 1
        elif status in manual_statuses:
            manual_author_judgment_count += 1
        elif explicit_author_judgment:
            weak_author_marker_count += 1
        else:
            continue
    return {
        "machine_solvable_count": machine_solvable_count,
        "machine_research_needed_count": machine_research_needed_count,
        "manual_author_judgment_count": manual_author_judgment_count,
        "weak_author_marker_count": weak_author_marker_count,
        "author_judgment_count": manual_author_judgment_count,
        "payload_unavailable": False,
    }


def _has_concrete_unbound_evidence_surface(item: dict[str, Any]) -> bool:
    evidence = item.get("evidence")
    if not isinstance(evidence, list):
        return False
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        locator = str(entry.get("url") or entry.get("source_url") or entry.get("source_title") or entry.get("title") or "").strip()
        support_text = str(
            entry.get("evidence_quote_or_summary")
            or entry.get("quoted_or_paraphrased_support")
            or entry.get("quote_or_summary")
            or entry.get("summary")
            or ""
        ).strip()
        if locator and support_text:
            return True
    return False


