from __future__ import annotations

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.engine.research_stages import (
    _citation_map_from_registry,
    _merge_live_verified_with_prior_registry,
)


def _paper(**overrides) -> VerifiedPaper:
    data = {
        "paper_id": "paper-1",
        "title": "A Useful Standard",
        "year": 2020,
        "publication_date": None,
        "venue": "Conference",
        "abstract": "abstract",
        "authors": ["A. Author"],
        "citation_count": 1,
        "external_ids": {},
        "url": "https://example.test/paper",
        "bibtex_key": "useful2020",
        "alias_bibtex_keys": [],
        "origin": "manual_seed",
        "matched_query": "useful standard",
        "title_match_ratio": 100.0,
        "is_after_cutoff": False,
    }
    data.update(overrides)
    return VerifiedPaper(**data)


def test_merge_live_registry_preserves_authoritative_prior_metadata() -> None:
    prior = _paper(
        paper_id="RFC-9000",
        venue="RFC Editor",
        url="https://www.rfc-editor.org/rfc/rfc9000",
        bibtex_key="rfc9000",
        alias_bibtex_keys=["quic"],
        external_ids={"DOI": "10.17487/RFC9000"},
        origin="manual_seed",
    )
    verified = _paper(
        paper_id="S2-QUIC",
        venue="Semantic Scholar",
        url="https://semanticscholar.org/paper/S2-QUIC",
        bibtex_key="iyengar2021quic",
        alias_bibtex_keys=["liveQuic"],
        external_ids={"CorpusId": "123"},
        origin="macro_candidates",
        citation_count=42,
    )

    merged = _merge_live_verified_with_prior_registry([prior], [verified])

    assert len(merged) == 1
    paper = merged[0]
    assert paper.paper_id == "RFC-9000"
    assert paper.venue == "RFC Editor"
    assert paper.url == "https://www.rfc-editor.org/rfc/rfc9000"
    assert paper.bibtex_key == "rfc9000"
    assert paper.citation_count == 42
    assert paper.external_ids["DOI"] == "10.17487/RFC9000"
    assert paper.external_ids["CorpusId"] == "123"
    assert paper.external_ids["VerifiedPaperId"] == "S2-QUIC"
    assert paper.external_ids["VerifiedURL"] == "https://semanticscholar.org/paper/S2-QUIC"
    assert paper.alias_bibtex_keys == ["quic", "iyengar2021quic"]
    assert paper.origin == "manual_seed+macro_candidates"


def test_citation_map_contains_canonical_and_alias_entries() -> None:
    paper = _paper(bibtex_key="canonical2024", alias_bibtex_keys=["aliasA", "aliasB"])

    citation_map = _citation_map_from_registry([paper])

    assert set(citation_map) == {"canonical2024", "aliasA", "aliasB"}
    assert citation_map["canonical2024"]["citation_key_role"] == "canonical"
    assert citation_map["aliasA"]["citation_key_role"] == "alias"
    assert citation_map["aliasB"]["canonical_bibtex_key"] == "canonical2024"
