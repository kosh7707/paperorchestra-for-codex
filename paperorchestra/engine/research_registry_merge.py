from __future__ import annotations

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.engine.research_registry_authority import merge_authoritative_external_ids, prior_work_metadata_is_authoritative
from paperorchestra.engine.research_registry_entry_merge import merge_verified_entry_with_prior_keys
from paperorchestra.engine.research_registry_titles import normalized_registry_title_key
from paperorchestra.research.bibtex import ensure_unique_bibtex_keys


def merge_live_verified_with_prior_registry(
    prior_registry: list[VerifiedPaper],
    verified_registry: list[VerifiedPaper],
) -> list[VerifiedPaper]:
    """Preserve curated citation keys while enriching with live verification."""

    if not prior_registry:
        return verified_registry
    if not verified_registry:
        return prior_registry

    merged_by_title: dict[str, VerifiedPaper] = {}
    ordered_titles: list[str] = []
    for paper in prior_registry:
        _remember_by_title(merged_by_title, ordered_titles, paper)
    for paper in verified_registry:
        title_key = normalized_registry_title_key(paper)
        if not title_key:
            continue
        prior = merged_by_title.get(title_key)
        _remember_title_key(
            merged_by_title,
            ordered_titles,
            title_key,
            paper if prior is None else merge_verified_entry_with_prior_keys(prior, paper),
        )
    return ensure_unique_bibtex_keys([merged_by_title[key] for key in ordered_titles if key in merged_by_title])


def _remember_by_title(merged_by_title: dict[str, VerifiedPaper], ordered_titles: list[str], paper: VerifiedPaper) -> None:
    title_key = normalized_registry_title_key(paper)
    if title_key:
        _remember_title_key(merged_by_title, ordered_titles, title_key, paper)


def _remember_title_key(
    merged_by_title: dict[str, VerifiedPaper],
    ordered_titles: list[str],
    title_key: str,
    paper: VerifiedPaper,
) -> None:
    if title_key not in merged_by_title:
        ordered_titles.append(title_key)
    merged_by_title[title_key] = paper
