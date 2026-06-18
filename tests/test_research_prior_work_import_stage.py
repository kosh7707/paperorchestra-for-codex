from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import ArtifactIndex, InputBundle, VerifiedPaper
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


def test_import_prior_work_keeps_legacy_facade_patch_surface(tmp_path: Path, monkeypatch) -> None:
    from paperorchestra.engine import research_prior_work_stage

    state = SimpleNamespace(
        inputs=SimpleNamespace(cutoff_date="2030-01-01"),
        artifacts=ArtifactIndex(),
        current_phase="init",
        active_artifact=None,
        latest_discovery_mode=None,
        notes=[],
    )
    registry = [
        VerifiedPaper(
            paper_id="p1",
            title="Facade Patch Surface",
            year=2026,
            publication_date=None,
            venue="TestConf",
            abstract="abstract",
            authors=["A. Author"],
            citation_count=1,
            bibtex_key="Facade2026",
        )
    ]
    calls: list[str] = []

    monkeypatch.setattr(research_prior_work_stage, "load_session", lambda cwd: state)
    monkeypatch.setattr(
        research_prior_work_stage,
        "load_prior_work_seed",
        lambda seed_file, *, source: calls.append(f"seed:{source}") or [{"title": "Facade Patch Surface"}],
    )
    monkeypatch.setattr(
        research_prior_work_stage,
        "prior_work_entries_to_verified_papers",
        lambda entries, *, cutoff_date: calls.append(f"registry:{cutoff_date}") or registry,
    )
    monkeypatch.setattr(research_prior_work_stage, "load_prior_citation_registry", lambda state, *, note_prefix: [])
    monkeypatch.setattr(
        research_prior_work_stage,
        "write_prior_work_import_artifacts",
        lambda cwd, registry_arg, *, source: {
            "candidate_papers_json": tmp_path / "candidate.json",
            "citation_registry_json": tmp_path / "registry.json",
            "citation_map_json": tmp_path / "map.json",
            "references_bib": tmp_path / "refs.bib",
        },
    )
    monkeypatch.setattr(research_prior_work_stage, "record_lane_manifest", lambda *args, **kwargs: tmp_path / "lane.json")
    monkeypatch.setattr(research_prior_work_stage, "save_session", lambda cwd, state: calls.append("save"))

    result = research_prior_work_stage.import_prior_work(tmp_path, seed_file=tmp_path / "seed.json", source="legacy_patch")

    assert calls == ["seed:legacy_patch", "registry:2030-01-01", "save"]
    assert result["references_bib"] == str(tmp_path / "refs.bib")
    assert state.artifacts.references_bib == str(tmp_path / "refs.bib")
