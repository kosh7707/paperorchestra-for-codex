from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json, write_text
from paperorchestra.core.session import artifact_path
from paperorchestra.engine.research_registry_payloads import citation_map_from_registry
from paperorchestra.research.bibtex import registry_to_bibtex
from paperorchestra.research.literature import serialize_registry


def write_prior_work_import_artifacts(cwd: str | Path | None, registry: list[Any], *, source: str) -> dict[str, Path]:
    candidate_payload = {
        "macro_candidates": [
            {
                "title_guess": paper.title,
                "why_relevant": paper.abstract,
                "origin_query": paper.matched_query or paper.title,
                "role_guess": "macro",
                "discovery_source": paper.origin or source,
                "discovery_sources": [paper.origin or source],
            }
            for paper in registry
        ],
        "micro_candidates": [],
    }
    candidate_path = artifact_path(cwd, "candidate_papers.json")
    registry_path = artifact_path(cwd, "citation_registry.json")
    citation_map_path = artifact_path(cwd, "citation_map.json")
    references_path = artifact_path(cwd, "references.bib")
    write_json(candidate_path, candidate_payload)
    serialize_registry(registry_path, registry)
    write_json(citation_map_path, citation_map_from_registry(registry))
    write_text(references_path, registry_to_bibtex(registry))
    return {
        "candidate_papers_json": candidate_path,
        "citation_registry_json": registry_path,
        "citation_map_json": citation_map_path,
        "references_bib": references_path,
    }
