from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json as _read_json, write_json as _write_json, write_text as _write_text
from paperorchestra.core.models import VerifiedPaper
from paperorchestra.core.session import artifact_path as _artifact_path, load_session as _load_session, save_session as _save_session
from paperorchestra.engine.research_registry import _citation_map_from_registry as _citation_map_from_registry_real
from paperorchestra.research.bibtex import registry_to_bibtex as _registry_to_bibtex


def _verification_dependency(name: str, default: Callable[..., Any]) -> Callable[..., Any]:
    stage = sys.modules.get("paperorchestra.engine.research_verification_stage")
    if stage is None:
        return default
    return getattr(stage, name, default)


def build_bib(cwd: str | Path | None) -> Path:
    state = _verification_dependency("load_session", _load_session)(cwd)
    if not state.artifacts.citation_registry_json:
        raise ContractError("Run verify-papers before build-bib.")
    registry = [VerifiedPaper(**item) for item in _verification_dependency("read_json", _read_json)(state.artifacts.citation_registry_json)]
    bib = _verification_dependency("registry_to_bibtex", _registry_to_bibtex)(registry)
    path = _verification_dependency("artifact_path", _artifact_path)(cwd, "references.bib")
    _verification_dependency("write_text", _write_text)(path, bib)
    citation_map_path = _verification_dependency("artifact_path", _artifact_path)(cwd, "citation_map.json")
    citation_map = _verification_dependency("_citation_map_from_registry", _citation_map_from_registry_real)(registry)
    _verification_dependency("write_json", _write_json)(citation_map_path, citation_map)
    state.artifacts.references_bib = str(path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.active_artifact = "references.bib"
    state.notes.append("BibTeX file generated.")
    _verification_dependency("save_session", _save_session)(cwd, state)
    return path
