from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine import research_verification_stage


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
