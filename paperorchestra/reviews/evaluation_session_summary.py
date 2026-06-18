from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.citations import canonical_citation_keys
from paperorchestra.reviews.evaluation_constants import (
    EXPECTED_SEARCH_GROUNDED_SOURCES,
    IGNORED_DISCOVERY_SOURCES,
)
from paperorchestra.reviews.evaluation_io import _write_json_artifact


def _session_artifact_dir(state) -> Path | None:
    for candidate in [state.artifacts.paper_full_tex, state.artifacts.candidate_papers_json]:
        if candidate and Path(candidate).exists():
            return Path(candidate).resolve().parent
    return None


def _attempted_grounded_sources(session_artifact_dir: Path | None) -> list[str]:
    if session_artifact_dir is None:
        return []
    lane_manifest_path = session_artifact_dir / "lane-manifest.literature.json"
    if not lane_manifest_path.exists():
        return []
    try:
        payload = read_json(lane_manifest_path)
    except Exception:
        return []
    notes = payload.get("notes", []) if isinstance(payload, dict) else []
    attempted: list[str] = []
    joined = "\n".join(note for note in notes if isinstance(note, str)).lower()
    if "semantic scholar grounded query" in joined and "semantic_scholar" not in attempted:
        attempted.append("semantic_scholar")
    if "openalex grounded query" in joined and "openalex" not in attempted:
        attempted.append("openalex")
    return attempted


def build_session_eval_summary(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    latest_review = read_json(state.artifacts.latest_review_json) if state.artifacts.latest_review_json and Path(state.artifacts.latest_review_json).exists() else None
    latest_fidelity = read_json(state.artifacts.latest_fidelity_json) if state.artifacts.latest_fidelity_json and Path(state.artifacts.latest_fidelity_json).exists() else None
    latest_runtime_parity = read_json(state.artifacts.latest_runtime_parity_json) if state.artifacts.latest_runtime_parity_json and Path(state.artifacts.latest_runtime_parity_json).exists() else None
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json and Path(state.artifacts.citation_map_json).exists() else {}
    candidate_papers = read_json(state.artifacts.candidate_papers_json) if state.artifacts.candidate_papers_json and Path(state.artifacts.candidate_papers_json).exists() else None
    validation_payload = read_json(state.artifacts.latest_validation_json) if state.artifacts.latest_validation_json and Path(state.artifacts.latest_validation_json).exists() else None
    session_artifact_dir = _session_artifact_dir(state)
    discovery_sources: list[str] = []
    candidate_count = 0
    if isinstance(candidate_papers, dict):
        for bucket in ("macro_candidates", "micro_candidates"):
            for candidate in candidate_papers.get(bucket, []):
                if not isinstance(candidate, dict):
                    continue
                candidate_count += 1
                sources = candidate.get("discovery_sources")
                if isinstance(sources, list) and sources:
                    for source in sources:
                        if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES and source not in discovery_sources:
                            discovery_sources.append(source)
                else:
                    source = candidate.get("discovery_source")
                    if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES and source not in discovery_sources:
                        discovery_sources.append(source)
    attempted_sources = _attempted_grounded_sources(session_artifact_dir)

    source_counts = {source: 0 for source in discovery_sources}
    if isinstance(candidate_papers, dict):
        for bucket in ("macro_candidates", "micro_candidates"):
            for candidate in candidate_papers.get(bucket, []):
                if not isinstance(candidate, dict):
                    continue
                sources = candidate.get("discovery_sources")
                if isinstance(sources, list) and sources:
                    for source in sources:
                        if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES:
                            source_counts[source] = source_counts.get(source, 0) + 1
                else:
                    source = candidate.get("discovery_source")
                    if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES:
                        source_counts[source] = source_counts.get(source, 0) + 1
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
