from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session
from paperorchestra.engine.research_prior_work_stage import import_prior_work


def _seed_session(tmp_path: Path) -> None:
    for name in ["idea.md", "experimental_log.md", "template.tex", "guidelines.md"]:
        (tmp_path / name).write_text(name, encoding="utf-8")
    create_session(
        tmp_path,
        InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experimental_log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
            cutoff_date="2030-01-01",
        ),
    )


def test_import_prior_work_writes_registry_candidates_references_and_session_state(tmp_path: Path) -> None:
    _seed_session(tmp_path)
    seed = tmp_path / "prior-work.json"
    write_json(
        seed,
        {
            "references": [
                {
                    "title": "Sifting the Noise for Static Analysis Triage",
                    "authors": ["A. Researcher"],
                    "year": 2024,
                    "venue": "ExampleConf",
                    "abstract": "Curated seed.",
                    "source": "manual_seed",
                    "bibtex_key": "Noise2024",
                }
            ]
        },
    )

    result = import_prior_work(tmp_path, seed_file=seed, source="manual_seed")

    state = load_session(tmp_path)
    assert result["candidate_papers_json"] == str(artifact_path(tmp_path, "candidate_papers.json"))
    assert Path(result["references_bib"]).read_text(encoding="utf-8")
    assert read_json(result["citation_registry_json"])[0]["bibtex_key"] == "Noise2024"
    assert read_json(result["citation_map_json"])
    assert state.artifacts.candidate_papers_json == result["candidate_papers_json"]
    assert state.artifacts.citation_registry_json == result["citation_registry_json"]
    assert state.artifacts.references_bib == result["references_bib"]
    assert state.current_phase == "literature_review"
