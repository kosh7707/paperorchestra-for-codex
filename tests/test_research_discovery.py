from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.engine.research_discovery import (
    _build_candidate_payload,
    _experimental_log_search_queries,
)


def _state(tmp_path: Path):
    idea = tmp_path / "idea.md"
    experimental_log = tmp_path / "experimental_log.md"
    template = tmp_path / "template.tex"
    guidelines = tmp_path / "guidelines.md"
    idea.write_text("idea", encoding="utf-8")
    experimental_log.write_text(
        "**Baselines:** CodeQL; Semgrep\n**Datasets / Benchmarks:** OWASP; CodeQL\n",
        encoding="utf-8",
    )
    template.write_text("template", encoding="utf-8")
    guidelines.write_text("guidelines", encoding="utf-8")
    inputs = SimpleNamespace(
        idea_path=str(idea),
        experimental_log_path=str(experimental_log),
        template_path=str(template),
        guidelines_path=str(guidelines),
        figures_dir=None,
        cutoff_date="2025-12-31",
    )
    return SimpleNamespace(inputs=inputs)


def _outline() -> dict:
    return {
        "intro_related_work_plan": {
            "introduction_strategy": {"search_directions": ["SAST alert triage"]},
            "related_work_strategy": {
                "subsections": [
                    {
                        "sota_investigation_mission": "LLM code review",
                        "limitation_search_queries": ["static analysis false positives"],
                    }
                ]
            },
        },
        "section_plan": [{"section": "Method"}],
    }


def test_experimental_log_queries_are_deduplicated_case_insensitively() -> None:
    assert _experimental_log_search_queries(
        "**Baselines:** CodeQL; codeql; Semgrep\n"
        "**Evaluation Metrics:** Precision, Recall; precision\n"
    ) == ["CodeQL", "Semgrep", "Precision", "Recall"]


def test_search_grounded_payload_selects_mock_mode_for_mock_provider(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_build_search_grounded_candidates(queries, **kwargs):
        captured["queries"] = queries
        captured.update(kwargs)
        return {"macro_candidates": [{"title_guess": "Macro"}], "micro_candidates": []}, ["grounded"]

    monkeypatch.delenv("PAPERO_SEARCH_GROUNDED_MODE", raising=False)
    monkeypatch.setitem(
        _build_candidate_payload.__globals__,
        "build_search_grounded_candidates",
        fake_build_search_grounded_candidates,
    )

    payload, lane_type, fallback_used, notes = _build_candidate_payload(
        _outline(),
        _state(tmp_path),
        SimpleNamespace(name="mock"),
        "search-grounded",
    )

    assert payload == {"macro_candidates": [{"title_guess": "Macro"}], "micro_candidates": []}
    assert lane_type == "python"
    assert fallback_used is False
    assert notes == ["grounded"]
    assert captured["mode"] == "mock"
    assert captured["cutoff_date"] == "2025-12-31"
    assert captured["macro_query_count"] == 1
    assert captured["queries"] == [
        "SAST alert triage",
        "LLM code review",
        "static analysis false positives",
        "CodeQL",
        "Semgrep",
        "OWASP",
    ]


def test_scholar_only_payload_maps_semantic_scholar_results_to_buckets(monkeypatch, tmp_path: Path) -> None:
    def fake_search_semantic_scholar(query, *, limit):
        return [{"title": f"{query} paper"}]

    monkeypatch.setitem(
        _build_candidate_payload.__globals__,
        "search_semantic_scholar",
        fake_search_semantic_scholar,
    )

    payload, lane_type, fallback_used, notes = _build_candidate_payload(
        _outline(),
        _state(tmp_path),
        provider=None,
        mode="scholar-only",
    )

    assert lane_type == "python"
    assert fallback_used is True
    assert notes == ["Scholar-only mode used Python discovery."]
    assert payload["macro_candidates"] == [
        {
            "title_guess": "SAST alert triage paper",
            "why_relevant": "Recovered from Semantic Scholar query result.",
            "origin_query": "SAST alert triage",
            "role_guess": "macro",
            "discovery_source": "semantic_scholar",
        }
    ]
    assert [item["role_guess"] for item in payload["micro_candidates"]] == ["micro"] * 5
