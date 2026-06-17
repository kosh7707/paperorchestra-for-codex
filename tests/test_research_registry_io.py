from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.engine import research_registry_io, research_stages


def _paper_payload(**overrides):
    data = {
        "paper_id": "paper-1",
        "title": "Prior Paper",
        "year": 2024,
        "publication_date": None,
        "venue": "Venue",
        "abstract": "Abstract",
        "authors": ["Ada"],
        "citation_count": 1,
        "external_ids": {},
        "url": "https://example.test",
        "bibtex_key": "prior2024",
        "alias_bibtex_keys": [],
        "origin": "manual_seed",
        "matched_query": "prior",
        "title_match_ratio": 100.0,
        "is_after_cutoff": False,
    }
    data.update(overrides)
    return data


def test_research_stages_facade_reexports_prior_registry_loader() -> None:
    assert research_stages.load_prior_citation_registry is research_registry_io.load_prior_citation_registry


def test_load_prior_citation_registry_returns_empty_without_artifact() -> None:
    state = SimpleNamespace(artifacts=SimpleNamespace(citation_registry_json=None), notes=[])

    assert research_registry_io.load_prior_citation_registry(state, note_prefix="Existing registry") == []
    assert state.notes == []


def test_load_prior_citation_registry_reads_verified_papers(tmp_path: Path) -> None:
    registry_path = tmp_path / "citation_registry.json"
    registry_path.write_text(
        '[{"paper_id":"paper-1","title":"Prior Paper","year":2024,"publication_date":null,'
        '"venue":"Venue","abstract":"Abstract","authors":["Ada"],"citation_count":1,'
        '"external_ids":{},"url":"https://example.test","bibtex_key":"prior2024",'
        '"alias_bibtex_keys":[],"origin":"manual_seed","matched_query":"prior",'
        '"title_match_ratio":100.0,"is_after_cutoff":false}]\n',
        encoding="utf-8",
    )
    state = SimpleNamespace(artifacts=SimpleNamespace(citation_registry_json=str(registry_path)), notes=[])

    registry = research_registry_io.load_prior_citation_registry(state, note_prefix="Existing registry")

    assert registry == [VerifiedPaper(**_paper_payload())]
    assert state.notes == []


def test_load_prior_citation_registry_notes_unreadable_payload(tmp_path: Path) -> None:
    registry_path = tmp_path / "citation_registry.json"
    registry_path.write_text("{not json", encoding="utf-8")
    state = SimpleNamespace(artifacts=SimpleNamespace(citation_registry_json=str(registry_path)), notes=[])

    registry = research_registry_io.load_prior_citation_registry(
        state,
        note_prefix="Existing citation registry could not be loaded during prior-work import",
    )

    assert registry == []
    assert state.notes == [
        "Existing citation registry could not be loaded during prior-work import and was treated as empty: JSONDecodeError."
    ]
