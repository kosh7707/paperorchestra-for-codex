from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_evidence_normalization import _clean_evidence
from paperorchestra.reviews.citation_evidence_standard_docs import (
    _citation_entry_standard_doc_references,
    _normalize_evidence_identity,
    _standard_doc_prefixed_title_matches_entry,
)


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
