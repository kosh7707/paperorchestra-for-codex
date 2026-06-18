from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.reviews.reproducibility_citation_provenance import _citation_registry_live_provenance
from paperorchestra.reviews.reproducibility_citations import _citation_surface_health


def _state(tmp_path: Path, tex: str, registry: list[dict], citation_map: dict, bib: str):
    paper = tmp_path / "paper.tex"
    registry_path = tmp_path / "citation_registry.json"
    map_path = tmp_path / "citation_map.json"
    bib_path = tmp_path / "references.bib"
    paper.write_text(tex, encoding="utf-8")
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    map_path.write_text(json.dumps(citation_map), encoding="utf-8")
    bib_path.write_text(bib, encoding="utf-8")
    artifacts = SimpleNamespace(
        paper_full_tex=str(paper),
        candidate_papers_json=None,
        citation_registry_json=str(registry_path),
        citation_map_json=str(map_path),
        references_bib=str(bib_path),
    )
    return SimpleNamespace(artifacts=artifacts, latest_verify_mode="live")


def test_citation_surface_health_accepts_consistent_artifacts(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        r"Evidence is discussed in \\cite{smith2024}.",
        [
            {
                "paper_id": "S2-1",
                "title": "Useful Paper",
                "year": 2024,
                "publication_date": None,
                "venue": "Conf",
                "abstract": "",
                "authors": ["A. Smith"],
                "citation_count": 3,
                "external_ids": {"DOI": "10/example"},
                "url": "https://example.test",
                "bibtex_key": "smith2024",
                "alias_bibtex_keys": [],
                "origin": "macro_candidates",
                "matched_query": "useful paper",
                "title_match_ratio": 1.0,
                "is_after_cutoff": False,
            }
        ],
        {
            "smith2024": {
                "title": "Useful Paper",
                "authors": ["A. Smith"],
                "year": 2024,
                "venue": "Conf",
                "paper_id": "S2-1",
                "origin": "macro_candidates",
            }
        },
        "@inproceedings{smith2024,\n  title={Useful Paper}\n}\n",
    )

    health = _citation_surface_health(state)

    assert health["status"] == "implemented"
    assert health["issues"] == []
    assert health["registry_keys"] == ["smith2024"]
    assert health["citation_map_keys"] == ["smith2024"]
    assert health["references_bib_keys"] == ["smith2024"]
    assert health["manuscript_citation_keys"] == ["smith2024"]


def test_citation_surface_health_reports_cross_artifact_gaps(tmp_path: Path) -> None:
    state = _state(
        tmp_path,
        r"Evidence is discussed in \\cite{missing_from_artifacts}.",
        [
            {
                "paper_id": "S2-1",
                "title": "Useful Paper",
                "year": 2024,
                "publication_date": None,
                "venue": "Conf",
                "abstract": "",
                "authors": ["A. Smith"],
                "citation_count": 3,
                "bibtex_key": "smith2024",
            }
        ],
        {"other2024": {"title": "Other Paper", "year": 2024}},
        "@article{smith2024,\n  title={Useful Paper}\n}\n",
    )

    health = _citation_surface_health(state)

    assert health["status"] == "partial"
    assert any("citation_map.json is missing registry key(s): smith2024" in issue for issue in health["issues"])
    assert any(
        "manuscript cites key(s) missing from citation_map.json: missing_from_artifacts" in issue
        for issue in health["issues"]
    )
    assert any(
        "manuscript cites key(s) missing from references.bib: missing_from_artifacts" in issue
        for issue in health["issues"]
    )


def test_citation_registry_live_provenance_scopes_to_cited_keys(tmp_path: Path) -> None:
    registry_path = tmp_path / "citation_registry.json"
    paper = tmp_path / "paper.tex"
    registry_path.write_text(
        json.dumps(
            [
                {
                    "paper_id": "S2-live",
                    "bibtex_key": "live2024",
                    "origin": "macro_candidates",
                    "authors": ["A"],
                    "venue": "Conf",
                },
                {
                    "paper_id": "S2-seed",
                    "bibtex_key": "unused_seed2024",
                    "origin": "metadata_seed_for_live_verification",
                    "authors": ["B"],
                    "venue": "Conf",
                },
            ]
        ),
        encoding="utf-8",
    )
    paper.write_text(r"Only one cited paper appears here \\cite{live2024}.", encoding="utf-8")

    provenance = _citation_registry_live_provenance(registry_path, paper)

    assert provenance["status"] == "live"
    assert provenance["registry_count"] == 2
    assert provenance["cited_entry_count"] == 1
    assert provenance["unused_registry_count"] == 1
    assert provenance["cited_live_verified_count"] == 1
    assert provenance["cited_curated_seed_count"] == 0
