from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import load_session
from paperorchestra.manuscript.narrative_contracts import planning_source_hashes
from paperorchestra.manuscript.narrative_sections import _section_titles, default_sections
from paperorchestra.manuscript.narrative_sources import _planning_source_text, _read_text


@dataclass(frozen=True)
class PlanningContext:
    state: Any
    citation_map: dict[str, Any]
    sections: list[str]
    log_planning_text: str
    template_planning_text: str
    planning_text: str
    author_source_text: str
    source_hashes: dict[str, str | None]


def load_planning_context(cwd: str | Path | None) -> PlanningContext:
    state = load_session(cwd)
    outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else {"section_plan": []}
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    idea_planning_text = _planning_source_text(_read_text(state.inputs.idea_path), preserve_numeric_percent=True)
    log_planning_text = _planning_source_text(
        _read_text(state.inputs.experimental_log_path),
        preserve_numeric_percent=True,
    )
    template_text = _read_text(state.inputs.template_path)
    template_planning_text = _planning_source_text(template_text)
    sections = _section_titles(outline, template_text) or default_sections()
    return PlanningContext(
        state=state,
        citation_map=citation_map if isinstance(citation_map, dict) else {},
        sections=sections,
        log_planning_text=log_planning_text,
        template_planning_text=template_planning_text,
        planning_text="\n".join([idea_planning_text, log_planning_text, template_planning_text]),
        author_source_text="\n".join([idea_planning_text, log_planning_text]),
        source_hashes=planning_source_hashes(cwd),
    )
