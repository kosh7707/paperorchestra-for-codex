from __future__ import annotations

from typing import Any


def _normalize_support_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "supported",
        "weakly_supported",
        "unsupported",
        "needs_manual_check",
        "metadata_only",
        "insufficient_evidence",
        "contradicted",
    }:
        return normalized
    if normalized in {"weak", "partial", "partially_supported"}:
        return "weakly_supported"
    if normalized in {"unknown", "unclear", "manual"}:
        return "needs_manual_check"
    if normalized in {"metadata", "title_overlap", "bibliographic_only"}:
        return "metadata_only"
    if normalized in {"insufficient", "not_found", "no_evidence"}:
        return "insufficient_evidence"
    return "needs_manual_check"


def _normalize_risk(value: Any, support_status: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    if support_status in {"unsupported", "contradicted"}:
        return "high"
    if support_status in {"weakly_supported", "needs_manual_check", "metadata_only", "insufficient_evidence"}:
        return "medium"
    return "low"


def _evidence_supports_claim(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "supports", "supported"}
    return False


def _clean_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        supports_raw = item.get("supports_claim")
        if supports_raw is None:
            supports_raw = item.get("supports")
        result.append(
            {
                "citation_key": item.get("citation_key"),
                "source_title": item.get("source_title") or item.get("title"),
                "url": item.get("url") or item.get("source_url"),
                "evidence_quote_or_summary": item.get("evidence_quote_or_summary")
                or item.get("quoted_or_paraphrased_support")
                or item.get("quote_or_summary")
                or item.get("summary"),
                "supports_claim": _evidence_supports_claim(supports_raw),
            }
        )
    return result
