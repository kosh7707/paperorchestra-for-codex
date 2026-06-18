from __future__ import annotations

import re
from typing import Any


def _coerce_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.search(r"\b(19|20)\d{2}\b", value)
        if match:
            return int(match.group(0))
    return None


def _split_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                result.append(item["name"].strip())
            elif isinstance(item, str):
                result.append(item.strip())
        return [item for item in result if item]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"\s+and\s+|;\s*|,\s*(?=[A-Z][A-Za-z]+(?:\s|$))", value) if item.strip()]
    return []


def _normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\b(10\.\d{4,9}/[^\s,;{}]+)", value)
    if not match:
        return None
    return match.group(1).rstrip(").,;")


def _entry_external_ids(entry: dict[str, Any]) -> dict[str, str]:
    external = entry.get("externalIds") or entry.get("external_ids") or {}
    result = {str(k): str(v) for k, v in external.items()} if isinstance(external, dict) else {}
    doi = entry.get("doi") or entry.get("DOI")
    normalized_doi = _normalize_doi(doi) if isinstance(doi, str) else None
    if normalized_doi:
        result["DOI"] = normalized_doi
    arxiv = entry.get("arxiv") or entry.get("ArXiv")
    if isinstance(arxiv, str) and arxiv.strip():
        result["ArXiv"] = arxiv.strip()
    return result


def _normalize_seed_entry(entry: dict[str, Any], *, default_source: str) -> dict[str, Any] | None:
    title = str(entry.get("title") or entry.get("paper_title") or "").strip()
    if not title:
        return None
    source = str(entry.get("source") or entry.get("provenance") or default_source).strip() or default_source
    authors = _split_authors(
        entry.get("authors")
        or entry.get("author")
        or entry.get("editors")
        or entry.get("editor")
        or entry.get("organization")
    )
    return {
        "title": title,
        "authors": authors,
        "bibtex_key": str(entry.get("bibtex_key") or "").strip() or None,
        "year": _coerce_year(entry.get("year") or entry.get("publication_year") or entry.get("date")),
        "year_source": (
            "year"
            if _coerce_year(entry.get("year")) is not None
            else "publication_year"
            if _coerce_year(entry.get("publication_year")) is not None
            else "date"
            if _coerce_year(entry.get("date")) is not None
            else None
        ),
        "publication_date": entry.get("publicationDate") or entry.get("publication_date"),
        "venue": str(entry.get("venue") or entry.get("journal") or entry.get("booktitle") or "").strip() or None,
        "abstract": str(entry.get("abstract") or entry.get("summary") or entry.get("notes") or f"Curated prior-work seed imported from {source}.").strip(),
        "citation_count": entry.get("citationCount") if isinstance(entry.get("citationCount"), int) else None,
        "external_ids": _entry_external_ids(entry),
        "url": str(entry.get("url") or entry.get("link") or "").strip() or None,
        "source": source,
        "provenance_notes": [
            str(item).strip()
            for item in (
                entry.get("provenance_notes")
                if isinstance(entry.get("provenance_notes"), list)
                else [entry.get("provenance_note") or entry.get("note") or ""]
            )
            if str(item).strip()
        ],
    }
