from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.reviews.evaluation_constants import IGNORED_DISCOVERY_SOURCES


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
    joined = "\n".join(note for note in notes if isinstance(note, str)).lower()
    attempted: list[str] = []
    if "semantic scholar grounded query" in joined:
        attempted.append("semantic_scholar")
    if "openalex grounded query" in joined:
        attempted.append("openalex")
    return attempted


def _candidate_discovery_summary(candidate_papers: Any) -> dict[str, Any]:
    discovery_sources: list[str] = []
    source_counts: dict[str, int] = {}
    candidate_count = 0
    if isinstance(candidate_papers, dict):
        for candidate in _iter_candidate_dicts(candidate_papers):
            candidate_count += 1
            for source in _candidate_sources(candidate):
                source_counts[source] = source_counts.get(source, 0) + 1
                if source not in discovery_sources:
                    discovery_sources.append(source)
    return {"count": candidate_count, "sources": discovery_sources, "source_counts": source_counts}


def _iter_candidate_dicts(candidate_papers: dict[str, Any]):
    for bucket in ("macro_candidates", "micro_candidates"):
        for candidate in candidate_papers.get(bucket, []):
            if isinstance(candidate, dict):
                yield candidate


def _candidate_sources(candidate: dict[str, Any]) -> list[str]:
    sources = candidate.get("discovery_sources")
    if isinstance(sources, list) and sources:
        return [source for source in sources if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES]
    source = candidate.get("discovery_source")
    return [source] if isinstance(source, str) and source not in IGNORED_DISCOVERY_SOURCES else []
