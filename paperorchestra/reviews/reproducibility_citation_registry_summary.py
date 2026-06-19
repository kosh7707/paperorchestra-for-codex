from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.manuscript.citation_key_parsing import extract_citation_keys
from paperorchestra.reviews.reproducibility_citation_entries import (
    _registry_entry_has_live_verification,
    _registry_entry_has_mixed_non_live_provenance,
    _registry_entry_is_mock,
    _registry_entry_key_aliases,
)

_EMPTY_REGISTRY_FIELDS = {
    "registry_count": 0,
    "live_verified_count": 0,
    "seed_only_count": 0,
    "mock_entry_count": 0,
    "live_coverage_ratio": 0.0,
    "cited_entry_count": 0,
    "unused_registry_count": 0,
    "cited_live_verified_count": 0,
    "cited_mixed_count": 0,
    "cited_curated_seed_count": 0,
    "cited_mock_count": 0,
}


def _empty_registry_provenance(status: str) -> dict[str, Any]:
    return {**_EMPTY_REGISTRY_FIELDS, "status": status}


def _cited_keys_from_paper(paper_path: str | Path | None) -> set[str] | None:
    if not paper_path:
        return None
    paper = Path(paper_path)
    if not paper.exists():
        return None
    return extract_citation_keys(paper.read_text(encoding="utf-8", errors="replace"))


def _citation_registry_provenance_from_entries(
    entries: list[dict[str, Any]],
    cited_keys: set[str] | None,
) -> dict[str, Any]:
    registry_count = len(entries)
    live_verified_count = sum(1 for item in entries if _registry_entry_has_live_verification(item))
    mock_entry_count = sum(1 for item in entries if _registry_entry_is_mock(item))
    seed_only_count = max(registry_count - live_verified_count - mock_entry_count, 0)
    live_coverage_ratio = (live_verified_count / registry_count) if registry_count else 0.0
    cited_entries = entries if cited_keys is None else [item for item in entries if _registry_entry_key_aliases(item) & cited_keys]
    cited_counts = _cited_provenance_counts(cited_entries)
    unused_registry_count = max(registry_count - cited_counts["cited_entry_count"], 0)
    return {
        "registry_count": registry_count,
        "live_verified_count": live_verified_count,
        "seed_only_count": seed_only_count,
        "mock_entry_count": mock_entry_count,
        "live_coverage_ratio": live_coverage_ratio,
        **cited_counts,
        "unused_registry_count": unused_registry_count,
        "status": _registry_provenance_status(
            registry_count=registry_count,
            mock_entry_count=mock_entry_count,
            seed_only_count=seed_only_count,
            cited_scope_active=cited_keys is not None,
            **cited_counts,
        ),
    }


def _cited_provenance_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    cited_entry_count = len(entries)
    cited_live_verified_count = sum(1 for item in entries if _registry_entry_has_live_verification(item))
    cited_mock_count = sum(1 for item in entries if _registry_entry_is_mock(item))
    cited_mixed_count = sum(
        1
        for item in entries
        if not _registry_entry_has_live_verification(item)
        and not _registry_entry_is_mock(item)
        and _registry_entry_has_mixed_non_live_provenance(item)
    )
    cited_curated_seed_count = max(
        cited_entry_count - cited_live_verified_count - cited_mock_count - cited_mixed_count,
        0,
    )
    return {
        "cited_entry_count": cited_entry_count,
        "cited_live_verified_count": cited_live_verified_count,
        "cited_mixed_count": cited_mixed_count,
        "cited_curated_seed_count": cited_curated_seed_count,
        "cited_mock_count": cited_mock_count,
    }


def _registry_provenance_status(
    *,
    registry_count: int,
    mock_entry_count: int,
    seed_only_count: int,
    cited_scope_active: bool,
    cited_entry_count: int,
    cited_live_verified_count: int,
    cited_mixed_count: int,
    cited_curated_seed_count: int,
    cited_mock_count: int,
) -> str:
    del cited_entry_count, cited_live_verified_count
    if not registry_count:
        return "empty"
    if cited_mock_count:
        return "mock"
    if cited_mixed_count:
        return "mixed"
    if cited_curated_seed_count:
        return "curated"
    if cited_scope_active:
        return "live"
    if mock_entry_count:
        return "mock"
    if seed_only_count:
        return "mixed"
    return "live"
