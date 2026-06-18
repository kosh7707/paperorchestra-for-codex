from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session


@dataclass(frozen=True)
class CitationReviewInputs:
    state: Any
    latex: str
    manuscript_sha256: str
    citation_map: dict[str, Any]
    citation_map_sha256: str | None


def _load_citation_review_inputs(cwd: str | Path | None) -> CitationReviewInputs:
    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ValueError("Need paper.full.tex before citation support review.")
    paper_path = Path(state.artifacts.paper_full_tex)
    latex = paper_path.read_text(encoding="utf-8")
    manuscript_sha256 = hashlib.sha256(paper_path.read_bytes()).hexdigest()
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    citation_map_sha256 = None
    if state.artifacts.citation_map_json and Path(state.artifacts.citation_map_json).exists():
        citation_map_sha256 = hashlib.sha256(Path(state.artifacts.citation_map_json).read_bytes()).hexdigest()
    return CitationReviewInputs(
        state=state,
        latex=latex,
        manuscript_sha256=manuscript_sha256,
        citation_map=citation_map,
        citation_map_sha256=citation_map_sha256,
    )
