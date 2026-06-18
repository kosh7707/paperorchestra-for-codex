from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import load_session
from paperorchestra.manuscript.narrative_sources import file_sha256

NARRATIVE_PLAN_SCHEMA_VERSION = "narrative-plan/1"
CLAIM_MAP_SCHEMA_VERSION = "claim-map/1"
CITATION_PLACEMENT_PLAN_SCHEMA_VERSION = "citation-placement-plan/1"


def planning_source_hashes(cwd: str | Path | None) -> dict[str, str | None]:
    state = load_session(cwd)
    return {
        "outline_json": file_sha256(state.artifacts.outline_json),
        "citation_map_json": file_sha256(state.artifacts.citation_map_json),
        "references_bib": file_sha256(state.artifacts.references_bib),
        "idea_md": file_sha256(state.inputs.idea_path),
        "experimental_log_md": file_sha256(state.inputs.experimental_log_path),
        "template_tex": file_sha256(state.inputs.template_path),
    }
