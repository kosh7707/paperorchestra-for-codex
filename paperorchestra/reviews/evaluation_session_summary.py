from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.citations import canonical_citation_keys
from paperorchestra.reviews.evaluation_constants import EXPECTED_SEARCH_GROUNDED_SOURCES
from paperorchestra.reviews.evaluation_discovery_summary import _attempted_grounded_sources, _candidate_discovery_summary
from paperorchestra.reviews.evaluation_io import _write_json_artifact


def _session_artifact_dir(state) -> Path | None:
    for candidate in [state.artifacts.paper_full_tex, state.artifacts.candidate_papers_json]:
        if candidate and Path(candidate).exists():
            return Path(candidate).resolve().parent
    return None


def _read_existing_json(path: str | Path | None, default: Any = None) -> Any:
    return read_json(path) if path and Path(path).exists() else default


def build_session_eval_summary(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    latest_review = _read_existing_json(state.artifacts.latest_review_json)
    latest_fidelity = _read_existing_json(state.artifacts.latest_fidelity_json)
    latest_runtime_parity = _read_existing_json(state.artifacts.latest_runtime_parity_json)
    citation_map = _read_existing_json(state.artifacts.citation_map_json, {})
    candidate_papers = _read_existing_json(state.artifacts.candidate_papers_json)
    validation_payload = _read_existing_json(state.artifacts.latest_validation_json)
    session_artifact_dir = _session_artifact_dir(state)
    discovery_summary = _candidate_discovery_summary(candidate_papers)
    discovery_sources = discovery_summary["sources"]
    source_counts = discovery_summary["source_counts"]
    candidate_count = discovery_summary["count"]
    attempted_sources = _attempted_grounded_sources(session_artifact_dir)
    search_grounded_sources_present = state.latest_discovery_mode == "search-grounded" and set(EXPECTED_SEARCH_GROUNDED_SOURCES) <= set(discovery_sources)
    search_grounded_attempted_sources_present = state.latest_discovery_mode == "search-grounded" and set(EXPECTED_SEARCH_GROUNDED_SOURCES) <= set(attempted_sources)

    return {
        "session_id": state.session_id,
        "current_phase": state.current_phase,
        "refinement_iteration": state.refinement_iteration,
        "review_overall_score": latest_review.get("overall_score") if isinstance(latest_review, dict) else None,
        "review_axis_scores": latest_review.get("axis_scores") if isinstance(latest_review, dict) else None,
        "verified_citation_count": len(canonical_citation_keys(citation_map)) if isinstance(citation_map, dict) else 0,
        "candidate_discovery_sources": discovery_sources,
        "candidate_discovery_source_counts": source_counts,
        "candidate_discovery_attempted_sources": attempted_sources,
        "candidate_discovery_mode": state.latest_discovery_mode,
        "search_grounded_required_sources_present": search_grounded_sources_present,
        "search_grounded_attempted_required_sources_present": search_grounded_attempted_sources_present,
        "candidate_count": candidate_count,
        "latest_validation": validation_payload,
        "fidelity_overall_status": latest_fidelity.get("overall_status") if isinstance(latest_fidelity, dict) else None,
        "runtime_parity_overall_status": latest_runtime_parity.get("overall_status") if isinstance(latest_runtime_parity, dict) else None,
        "artifacts": {
            "paper_full_tex": state.artifacts.paper_full_tex,
            "latest_review_json": state.artifacts.latest_review_json,
            "latest_fidelity_json": state.artifacts.latest_fidelity_json,
            "latest_runtime_parity_json": state.artifacts.latest_runtime_parity_json,
        },
        "notes_tail": state.notes[-6:],
    }


def write_session_eval_summary(cwd: str | Path | None, output_path: str | Path) -> Path:
    payload = build_session_eval_summary(cwd)
    return _write_json_artifact(payload, output_path)
