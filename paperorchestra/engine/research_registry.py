from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.literature import ensure_unique_bibtex_keys, is_citable_paper


def _registry_entry_payload(paper: VerifiedPaper, *, citation_key_role: str = "canonical") -> dict[str, Any]:
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


def _merge_live_verified_with_prior_registry(
    prior_registry: list[VerifiedPaper],
    verified_registry: list[VerifiedPaper],
) -> list[VerifiedPaper]:
    """Preserve curated citation keys while enriching with live verification.

    `import-prior-work` is the operator/human-curated bibliography surface.  A
    later Semantic Scholar verification pass may confirm only a subset of those
    entries (RFCs, NIST reports, web specs, and some standards are often not
    returned as paper records).  Claim-safe source packets still need those
    curated keys in citation_map.json, so live verification must merge with,
    not destructively replace, the prior registry.
    """

    if not prior_registry:
        return verified_registry
    if not verified_registry:
        return prior_registry

    merged_by_title: dict[str, VerifiedPaper] = {}
    ordered_titles: list[str] = []

    def remember(title_key: str, paper: VerifiedPaper) -> None:
        if title_key not in merged_by_title:
            ordered_titles.append(title_key)
        merged_by_title[title_key] = paper

    for paper in prior_registry:
        title_key = _normalized_registry_title_key(paper)
        if title_key:
            remember(title_key, paper)

    for paper in verified_registry:
        title_key = _normalized_registry_title_key(paper)
        if not title_key:
            continue
        prior = merged_by_title.get(title_key)
        if prior is None:
            remember(title_key, paper)
            continue
        remember(title_key, _merge_verified_entry_with_prior_keys(prior, paper))

    merged = [merged_by_title[key] for key in ordered_titles if key in merged_by_title]
    return ensure_unique_bibtex_keys(merged)


def _normalized_registry_title_key(paper: VerifiedPaper) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", paper.title.lower())).strip()


def _merge_verified_entry_with_prior_keys(prior: VerifiedPaper, verified: VerifiedPaper) -> VerifiedPaper:
    live_primary_key = verified.bibtex_key
    authoritative_prior = _prior_work_metadata_is_authoritative(prior)
    if authoritative_prior:
        canonical = VerifiedPaper(
            paper_id=prior.paper_id,
            title=prior.title,
            year=prior.year,
            publication_date=prior.publication_date,
            venue=prior.venue,
            abstract=prior.abstract,
            authors=list(prior.authors),
            citation_count=verified.citation_count if verified.citation_count is not None else prior.citation_count,
            external_ids=_merge_authoritative_external_ids(prior.external_ids or {}, verified.external_ids or {}),
            url=prior.url,
            bibtex_key=prior.bibtex_key,
            alias_bibtex_keys=list(prior.alias_bibtex_keys),
            origin=prior.origin,
            matched_query=prior.matched_query or verified.matched_query,
            title_match_ratio=max(
                value for value in [prior.title_match_ratio, verified.title_match_ratio] if value is not None
            )
            if (prior.title_match_ratio is not None or verified.title_match_ratio is not None)
            else None,
            is_after_cutoff=prior.is_after_cutoff or verified.is_after_cutoff,
        )
        if verified.paper_id and verified.paper_id != canonical.paper_id:
            canonical.external_ids.setdefault("VerifiedPaperId", verified.paper_id)
        if verified.url and verified.url != canonical.url:
            canonical.external_ids.setdefault("VerifiedURL", verified.url)
        if verified.origin and canonical.origin and verified.origin not in canonical.origin.split("+"):
            canonical.origin = f"{canonical.origin}+{verified.origin}"
        elif verified.origin and not canonical.origin:
            canonical.origin = verified.origin
        verified = canonical
    verified.bibtex_key = prior.bibtex_key or verified.bibtex_key
    aliases: list[str] = []
    for key in [*prior.alias_bibtex_keys, live_primary_key, *verified.alias_bibtex_keys]:
        if key and key != verified.bibtex_key and key not in aliases:
            aliases.append(key)
    verified.alias_bibtex_keys = aliases
    if prior.origin and verified.origin and prior.origin not in verified.origin.split("+"):
        verified.origin = f"{prior.origin}+{verified.origin}"
    elif prior.origin and not verified.origin:
        verified.origin = prior.origin
    if prior.matched_query and not verified.matched_query:
        verified.matched_query = prior.matched_query
    return verified


def _prior_work_metadata_is_authoritative(prior: VerifiedPaper) -> bool:
    """Return true when curated source metadata is more canonical than live paper search.

    Semantic Scholar/OpenAlex often return useful discovery records for standards
    documents but may carry stale years, Semantic Scholar landing URLs, or copied
    abstracts from nearby RFCs.  Imported RFC/NIST/FIPS seeds are intentionally the
    operator-curated bibliographic source of truth; live verification should enrich
    provenance, not replace the canonical rendered reference.
    """

    origin = str(prior.origin or "").lower()
    venue = str(prior.venue or "").lower()
    url = str(prior.url or "").lower()
    doi = " ".join(str(value).lower() for value in (prior.external_ids or {}).values())
    return any(
        marker in " ".join([origin, venue, url, doi])
        for marker in [
            "rfc editor",
            "rfc ",
            "rfc-",
            "rfc/",
            "10.17487/rfc",
            "nist",
            "fips",
            "sp 800",
            "10.6028/nist",
        ]
    )


def _merge_authoritative_external_ids(
    prior_external_ids: dict[str, str],
    verified_external_ids: dict[str, str],
) -> dict[str, str]:
    merged = dict(prior_external_ids)
    for key, value in verified_external_ids.items():
        if key not in merged:
            merged[key] = value
            continue
        if merged[key] == value:
            continue
        conflict_key = f"Verified{key}"
        suffix = 2
        while conflict_key in merged and merged[conflict_key] != value:
            conflict_key = f"Verified{key}{suffix}"
            suffix += 1
        merged.setdefault(conflict_key, value)
    return merged


def _citation_map_from_registry(registry: list[VerifiedPaper]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for paper in registry:
        if not is_citable_paper(paper):
            continue
        if paper.bibtex_key:
            payload[paper.bibtex_key] = _registry_entry_payload(paper, citation_key_role="canonical")
        for key in paper.alias_bibtex_keys:
            if key:
                payload[key] = _registry_entry_payload(paper, citation_key_role="alias")
    return payload
