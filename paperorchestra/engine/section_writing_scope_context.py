from __future__ import annotations

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_text
from paperorchestra.core.models import SessionState
from paperorchestra.engine.section_scope import _resolve_selected_sections


def _current_source_for_scope(state: SessionState, selected_sections: list[str]) -> tuple[str | None, list[str]]:
    if selected_sections and not state.artifacts.paper_full_tex:
        raise ContractError("Need an existing paper.full.tex before rewriting only selected sections.")
    current_source = (
        read_text(state.artifacts.paper_full_tex)
        if selected_sections and state.artifacts.paper_full_tex
        else None
    )
    if current_source is not None:
        selected_sections = _resolve_selected_sections(current_source, selected_sections)
    return current_source, selected_sections
