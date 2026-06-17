from __future__ import annotations

import pytest

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.bibtex import (
    ensure_unique_bibtex_keys,
    is_citable_paper,
    make_bibtex_key,
    registry_to_bibtex,
)
from paperorchestra.research.matching import grounded_result_is_relevant, normalize_title


def _paper(**overrides) -> VerifiedPaper:
    data = {
        "paper_id": "p1",
        "title": "Evidence-Grounded Alert Triage",
        "year": 2026,
        "publication_date": "2026-01-01",
        "venue": "Proceedings",
        "abstract": "Abstract",
        "authors": ["Ada Lovelace"],
        "citation_count": 10,
        "external_ids": {},
        "url": None,
        "bibtex_key": None,
    }
    data.update(overrides)
    return VerifiedPaper(**data)


def test_matching_normalizes_titles_and_filters_unrelated_long_queries() -> None:
    assert normalize_title("LLM-Based SAST Alert Triage!") == "llm based sast alert triage"
    assert grounded_result_is_relevant(
        "evidence grounded sast alert triage source finality benchmark",
        "Evidence-grounded SAST alert triage with source finality",
        "A benchmark for static-analysis alert triage.",
    )
    assert not grounded_result_is_relevant(
        "evidence grounded sast alert triage source finality benchmark",
        "Neural image generation for protein microscopy",
        "A paper about biological imaging.",
    )


def test_bibtex_keys_are_deterministic_and_deduplicated() -> None:
    first = _paper()
    second = _paper(paper_id="p2")

    assert make_bibtex_key(first) == "lovelace2026EvidenceGroundedAlert"

    ensure_unique_bibtex_keys([first, second])

    assert first.bibtex_key == "lovelace2026EvidenceGroundedAlert"
    assert second.bibtex_key == "lovelace2026EvidenceGroundedAlert2"


def test_registry_to_bibtex_escapes_values_and_skips_uncitable_entries() -> None:
    citable = _paper(
        bibtex_key="safe2026",
        title="A 50% Faster & Safer_ Pipeline",
        external_ids={"DOI": "10.1145/example"},
        url="https://example.test/paper",
    )
    uncitable = _paper(paper_id="p2", title="Unknown", year=None, publication_date=None, bibtex_key="bad")

    rendered = registry_to_bibtex([citable, uncitable])

    assert "@inproceedings{safe2026," in rendered
    assert "title = {A 50\\% Faster \\& Safer\\_ Pipeline}" in rendered
    assert "doi = {10.1145/example}" in rendered
    assert "bad" not in rendered
    assert is_citable_paper(citable)
    assert not is_citable_paper(uncitable)


def test_registry_to_bibtex_rejects_unbalanced_raw_braces() -> None:
    with pytest.raises(ValueError):
        registry_to_bibtex([_paper(bibtex_key="broken", title="Broken } Title")])
