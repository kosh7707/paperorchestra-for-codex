from __future__ import annotations

from typing import Any

from paperorchestra.research.prior_work_seed_authors import _split_authors
from paperorchestra.research.prior_work_seed_dates import _entry_year_with_source
from paperorchestra.research.prior_work_seed_external_ids import _entry_external_ids


def _normalize_seed_entry(entry: dict[str, Any], *, default_source: str) -> dict[str, Any] | None:
    title = str(entry.get("title") or entry.get("paper_title") or "").strip()
    if not title:
        return None
    source = str(entry.get("source") or entry.get("provenance") or default_source).strip() or default_source
    year, year_source = _entry_year_with_source(entry)
    return {
        "title": title,
        "authors": _entry_authors(entry),
        "bibtex_key": str(entry.get("bibtex_key") or "").strip() or None,
        "year": year,
        "year_source": year_source,
        "publication_date": entry.get("publicationDate") or entry.get("publication_date"),
        "venue": str(entry.get("venue") or entry.get("journal") or entry.get("booktitle") or "").strip() or None,
        "abstract": _entry_abstract(entry, source),
        "citation_count": entry.get("citationCount") if isinstance(entry.get("citationCount"), int) else None,
        "external_ids": _entry_external_ids(entry),
        "url": str(entry.get("url") or entry.get("link") or "").strip() or None,
        "source": source,
        "provenance_notes": _provenance_notes(entry),
    }


def _entry_authors(entry: dict[str, Any]) -> list[str]:
    return _split_authors(
        entry.get("authors")
        or entry.get("author")
        or entry.get("editors")
        or entry.get("editor")
        or entry.get("organization")
    )


def _entry_abstract(entry: dict[str, Any], source: str) -> str:
    return str(
        entry.get("abstract")
        or entry.get("summary")
        or entry.get("notes")
        or f"Curated prior-work seed imported from {source}."
    ).strip()


def _provenance_notes(entry: dict[str, Any]) -> list[str]:
    notes = entry.get("provenance_notes") if isinstance(entry.get("provenance_notes"), list) else [entry.get("provenance_note") or entry.get("note") or ""]
    return [str(item).strip() for item in notes if str(item).strip()]
