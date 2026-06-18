from __future__ import annotations

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.engine.research_registry_authority import (
    merge_authoritative_external_ids,
    prior_work_metadata_is_authoritative,
)


def merge_verified_entry_with_prior_keys(prior: VerifiedPaper, verified: VerifiedPaper) -> VerifiedPaper:
    live_primary_key = verified.bibtex_key
    if prior_work_metadata_is_authoritative(prior):
        verified = _authoritative_prior_entry(prior, verified)
    verified.bibtex_key = prior.bibtex_key or verified.bibtex_key
    verified.alias_bibtex_keys = _merged_aliases(prior, live_primary_key, verified)
    verified.origin = _merged_origin(prior.origin, verified.origin)
    if prior.matched_query and not verified.matched_query:
        verified.matched_query = prior.matched_query
    return verified


def _authoritative_prior_entry(prior: VerifiedPaper, verified: VerifiedPaper) -> VerifiedPaper:
    canonical = VerifiedPaper(
        paper_id=prior.paper_id,
        title=prior.title,
        year=prior.year,
        publication_date=prior.publication_date,
        venue=prior.venue,
        abstract=prior.abstract,
        authors=list(prior.authors),
        citation_count=verified.citation_count if verified.citation_count is not None else prior.citation_count,
        external_ids=merge_authoritative_external_ids(prior.external_ids or {}, verified.external_ids or {}),
        url=prior.url,
        bibtex_key=prior.bibtex_key,
        alias_bibtex_keys=list(prior.alias_bibtex_keys),
        origin=prior.origin,
        matched_query=prior.matched_query or verified.matched_query,
        title_match_ratio=_best_title_match_ratio(prior, verified),
        is_after_cutoff=prior.is_after_cutoff or verified.is_after_cutoff,
    )
    _remember_verified_identity(canonical, verified)
    canonical.origin = _merged_origin(canonical.origin, verified.origin)
    return canonical


def _remember_verified_identity(canonical: VerifiedPaper, verified: VerifiedPaper) -> None:
    if verified.paper_id and verified.paper_id != canonical.paper_id:
        canonical.external_ids.setdefault("VerifiedPaperId", verified.paper_id)
    if verified.url and verified.url != canonical.url:
        canonical.external_ids.setdefault("VerifiedURL", verified.url)


def _best_title_match_ratio(prior: VerifiedPaper, verified: VerifiedPaper) -> float | None:
    values = [value for value in (prior.title_match_ratio, verified.title_match_ratio) if value is not None]
    return max(values) if values else None


def _merged_aliases(prior: VerifiedPaper, live_primary_key: str, verified: VerifiedPaper) -> list[str]:
    aliases: list[str] = []
    for key in [*prior.alias_bibtex_keys, live_primary_key, *verified.alias_bibtex_keys]:
        if key and key != verified.bibtex_key and key not in aliases:
            aliases.append(key)
    return aliases


def _merged_origin(prior_origin: str | None, verified_origin: str | None) -> str | None:
    if prior_origin and verified_origin:
        if prior_origin not in verified_origin.split("+"):
            return f"{prior_origin}+{verified_origin}"
        return verified_origin
    return prior_origin or verified_origin
