from __future__ import annotations

from typing import Any

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.bibtex import is_citable_paper


def registry_entry_payload(paper: VerifiedPaper, *, citation_key_role: str = "canonical") -> dict[str, Any]:
    return {
        "canonical_bibtex_key": paper.bibtex_key,
        "alias_bibtex_keys": list(paper.alias_bibtex_keys),
        "citation_key_role": citation_key_role,
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "paper_id": paper.paper_id,
        "url": paper.url,
        "external_ids": paper.external_ids,
        "origin": paper.origin,
        "matched_query": paper.matched_query,
        "provenance": {
            "source": paper.origin,
            "verification": "curated_seed" if paper.origin and "seed" in paper.origin else "metadata_import",
            "title_match_ratio": paper.title_match_ratio,
        },
    }


def citation_map_from_registry(registry: list[VerifiedPaper]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for paper in registry:
        if not is_citable_paper(paper):
            continue
        if paper.bibtex_key:
            payload[paper.bibtex_key] = registry_entry_payload(paper, citation_key_role="canonical")
        for key in paper.alias_bibtex_keys:
            if key:
                payload[key] = registry_entry_payload(paper, citation_key_role="alias")
    return payload
