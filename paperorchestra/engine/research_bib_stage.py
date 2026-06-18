from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json, write_text
from paperorchestra.core.models import VerifiedPaper
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.research_registry import _citation_map_from_registry
from paperorchestra.research.bibtex import registry_to_bibtex


def build_bib(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if not state.artifacts.citation_registry_json:
        raise ContractError("Run verify-papers before build-bib.")
    registry = [VerifiedPaper(**item) for item in read_json(state.artifacts.citation_registry_json)]
    bib = registry_to_bibtex(registry)
    path = artifact_path(cwd, "references.bib")
    write_text(path, bib)
    citation_map_path = artifact_path(cwd, "citation_map.json")
    write_json(citation_map_path, _citation_map_from_registry(registry))
    state.artifacts.references_bib = str(path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.active_artifact = "references.bib"
    state.notes.append("BibTeX file generated.")
    save_session(cwd, state)
    return path
