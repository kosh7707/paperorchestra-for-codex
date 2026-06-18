from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import ArtifactIndex, InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine.research_candidate_verification import verify_candidate_registry
from paperorchestra.engine import research_verification_stage
from paperorchestra.research.literature import mock_verified_paper


def _session_with_candidates(tmp_path: Path) -> None:
    for name, content in {
        "idea.md": "idea",
        "experimental_log.md": "experiment",
        "template.tex": "template",
        "guidelines.md": "guidelines",
    }.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experimental_log.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
            cutoff_date="2030-01-01",
        ),
    )
    candidate_path = artifact_path(tmp_path, "candidate-papers.json")
    write_json(
        candidate_path,
        {
            "macro_candidates": [
                {
                    "title_guess": "Evidence Grounded Agents for SAST Alert Triage",
                    "why_relevant": "pipeline evidence",
                    "origin_query": "sast alert triage llm",
                }
            ],
            "micro_candidates": [],
        },
    )
    state.artifacts.candidate_papers_json = str(candidate_path)
    save_session(tmp_path, state)


def test_verify_papers_mock_writes_registry_map_and_session_state(tmp_path: Path) -> None:
    _session_with_candidates(tmp_path)

    registry_path = research_verification_stage.verify_papers(tmp_path, mode="mock")

    registry = read_json(registry_path)
    citation_map = read_json(artifact_path(tmp_path, "citation_map.json"))
    state = load_session(tmp_path)
    assert len(registry) == 1
    assert registry[0]["origin"] == "macro_candidates"
    assert citation_map
    assert state.artifacts.citation_registry_json == str(registry_path)
    assert state.artifacts.citation_map_json == str(artifact_path(tmp_path, "citation_map.json"))
    assert state.latest_verify_mode == "mock"
    assert state.active_artifact == "citation_registry.json"


def test_verify_papers_live_fail_records_errors_and_blocks_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _session_with_candidates(tmp_path)

    def fail_verify(*args, **kwargs):
        raise RuntimeError("semantic scholar down")

    monkeypatch.setattr(research_verification_stage, "verify_candidate_title", fail_verify)

    with pytest.raises(ContractError, match="Live verification failed"):
        research_verification_stage.verify_papers(tmp_path, mode="live", on_error="fail")

    state = load_session(tmp_path)
    errors = read_json(artifact_path(tmp_path, "verification_errors.json"))
    assert state.current_phase == "blocked"
    assert state.active_artifact == "verification_errors.json"
    assert state.artifacts.latest_verification_errors_json == str(artifact_path(tmp_path, "verification_errors.json"))
    assert errors["error_count"] == 1
    assert errors["errors"][0]["action"] == "failed"
    assert errors["errors"][0]["title_guess"] == "Evidence Grounded Agents for SAST Alert Triage"


def test_candidate_registry_live_skip_collects_errors_and_dedupes_verified_papers() -> None:
    candidates = {
        "macro_candidates": [
            {"title_guess": "Verified Paper", "origin_query": "verified"},
            {"title_guess": "Broken Paper", "origin_query": "broken"},
        ],
        "micro_candidates": [
            {"title_guess": "Verified Paper", "origin_query": "duplicate"},
        ],
    }

    def verifier(title: str, **kwargs):
        if title == "Broken Paper":
            raise RuntimeError("semantic scholar down")
        return mock_verified_paper(title, abstract_hint="", cutoff_date="2030-01-01")

    result = verify_candidate_registry(
        candidates,
        cutoff_date="2030-01-01",
        mode="live",
        min_ratio=70.0,
        on_error="skip",
        live_verifier=verifier,
    )

    assert len(result.registry) == 1
    assert result.errors[0]["title_guess"] == "Broken Paper"
    assert result.errors[0]["action"] == "skipped"
    assert result.candidate_count == 3


def test_build_bib_writes_references_and_updates_session_state(tmp_path: Path) -> None:
    _session_with_candidates(tmp_path)
    research_verification_stage.verify_papers(tmp_path, mode="mock")

    bib_path = research_verification_stage.build_bib(tmp_path)

    state = load_session(tmp_path)
    citation_map = read_json(artifact_path(tmp_path, "citation_map.json"))
    assert bib_path == artifact_path(tmp_path, "references.bib")
    assert "Evidence Grounded Agents" in bib_path.read_text(encoding="utf-8")
    assert citation_map
    assert state.artifacts.references_bib == str(bib_path)
    assert state.artifacts.citation_map_json == str(artifact_path(tmp_path, "citation_map.json"))
    assert state.active_artifact == "references.bib"


def test_build_bib_keeps_legacy_facade_patch_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = SimpleNamespace(
        artifacts=ArtifactIndex(citation_registry_json=str(tmp_path / "registry.json")),
        active_artifact=None,
        notes=[],
    )
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(research_verification_stage, "load_session", lambda cwd: state)
    monkeypatch.setattr(
        research_verification_stage,
        "read_json",
        lambda path: [
            {
                "paper_id": "p1",
                "title": "Facade Bib Surface",
                "year": 2026,
                "publication_date": None,
                "venue": "TestConf",
                "abstract": "abstract",
                "authors": ["A. Author"],
                "citation_count": 1,
                "bibtex_key": "Facade2026",
            }
        ],
    )
    monkeypatch.setattr(research_verification_stage, "registry_to_bibtex", lambda registry: "@article{Facade2026}")
    monkeypatch.setattr(research_verification_stage, "artifact_path", lambda cwd, name: tmp_path / name)
    monkeypatch.setattr(research_verification_stage, "write_text", lambda path, text: calls.append(("text", text)))
    monkeypatch.setattr(research_verification_stage, "write_json", lambda path, payload: calls.append(("json", payload)))
    monkeypatch.setattr(research_verification_stage, "_citation_map_from_registry", lambda registry: {"Facade2026": "Facade Bib Surface"})
    monkeypatch.setattr(research_verification_stage, "save_session", lambda cwd, state: calls.append(("save", state.active_artifact)))

    bib_path = research_verification_stage.build_bib(tmp_path)

    assert bib_path == tmp_path / "references.bib"
    assert calls == [
        ("text", "@article{Facade2026}"),
        ("json", {"Facade2026": "Facade Bib Surface"}),
        ("save", "references.bib"),
    ]
    assert state.artifacts.references_bib == str(tmp_path / "references.bib")
