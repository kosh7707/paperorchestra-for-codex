from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.citations import canonical_citation_map

from paperorchestra.engine.prompt_markup import _prompt_compact_text


def _compact_citation_map_for_prompt(
    citation_map: dict[str, Any],
    *,
    title_limit: int = 140,
    abstract_limit: int = 220,
    max_authors: int = 4,
    include_abstract: bool = True,
    include_authors: bool = True,
    include_year: bool = True,
    include_venue: bool = True,
    include_provenance: bool = True,
    include_origin: bool = True,
    include_matched_query: bool = True,
) -> dict[str, Any]:
    citation_map = canonical_citation_map(citation_map)
    compact: dict[str, Any] = {}
    for key, value in citation_map.items():
        if not isinstance(value, dict):
            compact[key] = value
            continue
        authors = value.get("authors")
        if include_authors and isinstance(authors, list):
            compact_authors = authors[:max_authors]
        elif include_authors:
            compact_authors = authors
        else:
            compact_authors = None
        abstract = value.get("abstract")
        if include_abstract and isinstance(abstract, str):
            compact_abstract = _prompt_compact_text(abstract, head_chars=abstract_limit, tail_chars=0)
        elif include_abstract:
            compact_abstract = abstract
        else:
            compact_abstract = None
        provenance = value.get("provenance")
        title = value.get("title")
        if isinstance(title, str):
            title = _prompt_compact_text(title, head_chars=title_limit, tail_chars=0)
        entry = {"title": title}
        if include_authors:
            entry["authors"] = compact_authors
        if include_abstract:
            entry["abstract"] = compact_abstract
        if include_year:
            entry["year"] = value.get("year")
        if include_venue:
            entry["venue"] = value.get("venue")
        if include_provenance:
            entry["provenance"] = provenance.get("source") if isinstance(provenance, dict) else provenance
        if include_origin:
            entry["origin"] = value.get("origin")
        if include_matched_query:
            entry["matched_query"] = value.get("matched_query")
        compact[key] = entry
    return compact
