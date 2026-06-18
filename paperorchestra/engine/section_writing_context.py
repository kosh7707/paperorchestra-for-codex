from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import SessionState
from paperorchestra.engine.prompt_context import (
    _raise_if_strict_source_citations_unmapped,
    _read_inputs,
    _source_critical_context_for_prompt,
    _strict_content_gates_enabled,
)
from paperorchestra.engine.section_writing_artifact_contexts import (
    _citation_context,
    _outline_context,
    _plot_context,
    _template_context,
)
from paperorchestra.engine.section_writing_planning_context import _planning_payloads
from paperorchestra.engine.section_writing_scope_context import _current_source_for_scope
from paperorchestra.engine.section_writing_types import SectionPromptContext


def build_section_prompt_context(
    cwd: str | Path | None,
    state: SessionState,
    *,
    selected_sections: list[str],
    claim_safe: bool,
) -> SectionPromptContext:
    current_source, selected_sections = _current_source_for_scope(state, selected_sections)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    planning = _planning_payloads(cwd, selected_sections)
    outline = _outline_context(state, selected_sections)
    citations = _citation_context(
        state,
        current_source=current_source,
        selected_sections=selected_sections,
        strict_claim_safe_prompt=strict_claim_safe_prompt,
    )
    template = _template_context(state, current_source=current_source, selected_sections=selected_sections)
    plots = _plot_context(state, selected_sections=selected_sections, selected_section_source=template.template_content)
    inputs = _read_inputs(state)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citations.citation_map,
        stage="section_writing",
        strict_claim_safe=strict_claim_safe_prompt,
    )
    return SectionPromptContext(
        selected_sections=selected_sections,
        current_source=current_source,
        planning=planning,
        outline=outline,
        citations=citations,
        plots=plots,
        template=template,
        inputs=inputs,
        source_critical_context=_source_critical_context_for_prompt(inputs),
        figures_dir=state.inputs.figures_dir,
        strict_claim_safe_prompt=strict_claim_safe_prompt,
    )


__all__ = [
    "_citation_context",
    "_current_source_for_scope",
    "_outline_context",
    "_planning_payloads",
    "_plot_context",
    "_template_context",
    "build_section_prompt_context",
]
