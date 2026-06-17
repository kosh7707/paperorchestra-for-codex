from __future__ import annotations

import re
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


def _normalize_evidence_identity(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _standard_doc_references(value: Any) -> set[tuple[str, str]]:
    normalized = _normalize_evidence_identity(value)
    refs: set[tuple[str, str]] = set()
    for match in re.finditer(r"\brfc\s*(\d+[a-z0-9]*)\b", normalized):
        refs.add(("rfc", match.group(1)))
    for match in re.finditer(
        r"\bnist\s+sp\s+(\d+(?:\s+\d+[a-z0-9]*)?)(?:\s+(?:part|pt)\s+(\d+))?(?:\s+rev\s+(\d+))?",
        normalized,
    ):
        identifier = " ".join(part for part in match.groups() if part).strip()
        if identifier:
            refs.add(("nist_sp", identifier))
    return refs


def _standard_doc_label_references(value: Any) -> set[tuple[str, str]]:
    normalized = _normalize_evidence_identity(value)
    refs: set[tuple[str, str]] = set()
    match = re.fullmatch(r"rfc\s*(\d+[a-z0-9]*)", normalized)
    if match:
        refs.add(("rfc", match.group(1)))
    match = re.fullmatch(
        r"nist\s+sp\s+(\d+(?:\s+\d+[a-z0-9]*)?)(?:\s+(?:part|pt)\s+(\d+))?(?:\s+rev\s+(\d+))?",
        normalized,
    )
    if match:
        identifier = " ".join(part for part in match.groups() if part).strip()
        if identifier:
            refs.add(("nist_sp", identifier))
    return refs


def _citation_entry_standard_doc_references(entry: dict[str, Any]) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for field in ("key", "title", "booktitle", "venue", "journal", "url", "doi", "howpublished"):
        refs.update(_standard_doc_references(entry.get(field)))
    return refs


def _standard_doc_prefixed_title_matches_entry(
    *,
    evidence_title: str,
    entry_title: str,
    entry_refs: set[tuple[str, str]],
) -> bool:
    if not evidence_title or not entry_refs:
        return False
    if entry_title and evidence_title.endswith(entry_title):
        prefix = evidence_title[: -len(entry_title)].strip()
        if _standard_doc_label_references(prefix) & entry_refs:
            return True
    return False


def _evidence_matches_citation_entry(entry: dict[str, Any], evidence_entry: dict[str, Any]) -> bool:
    evidence_url = str(evidence_entry.get("url") or "").strip().rstrip("/")
    entry_url = str(entry.get("url") or "").strip().rstrip("/")
    if evidence_url and entry_url and evidence_url == entry_url:
        return True
    evidence_title = _normalize_evidence_identity(evidence_entry.get("source_title"))
    entry_title = _normalize_evidence_identity(entry.get("title"))
    if evidence_title and entry_title and evidence_title == entry_title:
        return True
    if _standard_doc_prefixed_title_matches_entry(
        evidence_title=evidence_title,
        entry_title=entry_title,
        entry_refs=_citation_entry_standard_doc_references(entry),
    ):
        return True
    return False


def _valid_cited_source_evidence(evidence: list[dict[str, Any]], item: dict[str, Any]) -> bool:
    allowed_keys = {str(key) for key in (item.get("citation_keys") or [])}
    entries_by_key = {
        str(entry.get("key")): entry
        for entry in (item.get("citation_entries") or [])
        if isinstance(entry, dict) and entry.get("key") is not None
    }
    for entry in evidence:
        if not entry.get("supports_claim"):
            continue
        citation_key = str(entry.get("citation_key") or "").strip()
        url = str(entry.get("url") or "").strip()
        source_title = str(entry.get("source_title") or "").strip()
        support_text = str(entry.get("evidence_quote_or_summary") or "").strip()
        if not support_text:
            continue
        if not (url or source_title):
            continue
        if citation_key and citation_key in allowed_keys and _evidence_matches_citation_entry(entries_by_key.get(citation_key, {}), entry):
            return True
    return False


def citation_item_has_valid_supporting_evidence(item: dict[str, Any]) -> bool:
    evidence = _clean_evidence(item.get("evidence"))
    return _valid_cited_source_evidence(evidence, item)


