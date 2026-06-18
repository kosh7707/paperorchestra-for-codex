from __future__ import annotations

import hashlib
from typing import Any

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.bibtex import ensure_unique_bibtex_keys, make_bibtex_key
from paperorchestra.research.dates import year_month_passes_cutoff
from paperorchestra.research.matching import normalize_title
from paperorchestra.research.prior_work_seed_parsers import _coerce_year, _split_authors


def prior_work_entries_to_verified_papers(
    entries: list[dict[str, Any]],
    *,
    cutoff_date: str | None = None,
) -> list[VerifiedPaper]:
    registry: list[VerifiedPaper] = []
    seen: dict[str, VerifiedPaper] = {}
    for index, entry in enumerate(entries, start=1):
        title = str(entry.get("title") or "").strip()
        normalized = normalize_title(title)
        if not normalized:
            continue
        year = _coerce_year(entry.get("year"))
        publication_date = entry.get("publication_date") if isinstance(entry.get("publication_date"), str) else None
        if not year_month_passes_cutoff(year, cutoff_date, publication_date):
            continue
        source = str(entry.get("source") or "manual_seed")
        key_hint = str(entry.get("bibtex_key") or "").strip() or None
        existing = seen.get(normalized)
        if existing is not None:
            if key_hint and key_hint != existing.bibtex_key and key_hint not in existing.alias_bibtex_keys:
                existing.alias_bibtex_keys.append(key_hint)
            continue
        paper = VerifiedPaper(
            paper_id=f"{source}:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}",
            title=title,
            year=year,
            publication_date=publication_date,
            venue=entry.get("venue") if isinstance(entry.get("venue"), str) else None,
            abstract=str(entry.get("abstract") or f"Curated prior-work seed imported from {source}."),
            authors=_split_authors(entry.get("authors")),
            citation_count=entry.get("citation_count") if isinstance(entry.get("citation_count"), int) else None,
            external_ids=entry.get("external_ids") if isinstance(entry.get("external_ids"), dict) else {},
            url=entry.get("url") if isinstance(entry.get("url"), str) else None,
            origin=source,
            matched_query=title,
            title_match_ratio=100.0,
            is_after_cutoff=False,
        )
        paper.bibtex_key = str(key_hint).strip() if isinstance(key_hint, str) and str(key_hint).strip() else make_bibtex_key(paper)
        registry.append(paper)
        seen[normalized] = paper
    registry = ensure_unique_bibtex_keys(registry)
    used_keys = {paper.bibtex_key for paper in registry if paper.bibtex_key}
    for paper in registry:
        deduped_aliases: list[str] = []
        for alias in paper.alias_bibtex_keys:
            if not alias or alias == paper.bibtex_key or alias in used_keys:
                continue
            used_keys.add(alias)
            deduped_aliases.append(alias)
        paper.alias_bibtex_keys = deduped_aliases
    return registry
