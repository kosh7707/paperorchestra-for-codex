from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.reviews import evaluation_session_summary as summary


def test_candidate_discovery_summary_counts_sources_and_ignores_local_artifacts() -> None:
    candidate_papers = {
        "macro_candidates": [
            {"discovery_sources": ["semantic_scholar", "manual_seed"]},
            {"discovery_source": "openalex"},
        ],
        "micro_candidates": [
            {"discovery_sources": ["semantic_scholar", "codex_web_seed"]},
            "bad",
        ],
    }

    result = summary._candidate_discovery_summary(candidate_papers)

    assert result["count"] == 3
    assert result["sources"] == ["semantic_scholar", "manual_seed", "openalex", "codex_web_seed"]
    assert result["source_counts"] == {"semantic_scholar": 2, "manual_seed": 1, "openalex": 1, "codex_web_seed": 1}


def test_attempted_grounded_sources_reads_lane_manifest_notes(tmp_path: Path) -> None:
    (tmp_path / "lane-manifest.literature.json").write_text(
        json.dumps({"notes": ["Semantic Scholar grounded query executed", "OpenAlex grounded query executed"]}),
        encoding="utf-8",
    )

    assert summary._attempted_grounded_sources(tmp_path) == ["semantic_scholar", "openalex"]


def test_build_session_eval_summary_preserves_facade_monkeypatch_surface(monkeypatch, tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"overall_score": 91, "axis_scores": {"clarity": 90}}), encoding="utf-8")
    citation_map = tmp_path / "citation-map.json"
    citation_map.write_text(json.dumps({"A": {"canonical_bibtex_key": "A"}}), encoding="utf-8")
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps({"macro_candidates": [{"discovery_source": "semantic_scholar"}]}), encoding="utf-8")
    state = SimpleNamespace(
        session_id="po-test",
        current_phase="review",
        refinement_iteration=2,
        latest_discovery_mode="search-grounded",
        notes=["a", "b"],
        artifacts=SimpleNamespace(
            paper_full_tex=None,
            latest_review_json=str(review),
            latest_fidelity_json=None,
            latest_runtime_parity_json=None,
            citation_map_json=str(citation_map),
            candidate_papers_json=str(candidates),
            latest_validation_json=None,
        ),
    )
    monkeypatch.setattr(summary, "load_session", lambda cwd: state)

    payload = summary.build_session_eval_summary(tmp_path)

    assert payload["session_id"] == "po-test"
    assert payload["review_overall_score"] == 91
    assert payload["verified_citation_count"] == 1
    assert payload["candidate_count"] == 1
    assert payload["candidate_discovery_sources"] == ["semantic_scholar"]
