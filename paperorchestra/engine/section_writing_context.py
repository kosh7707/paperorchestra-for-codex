from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_text
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
from paperorchestra.engine.planning_payloads import (
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.section_scope import _resolve_selected_sections
from paperorchestra.engine.section_writing_types import PlanningPromptPayloads, SectionPromptContext
from paperorchestra.manuscript.skeleton import paper_skeleton_status


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


def _planning_payloads(cwd: str | Path | None, selected_sections: list[str]) -> PlanningPromptPayloads:
    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        selected_sections,
    )
    return PlanningPromptPayloads(
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
        writer_brief=_writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan),
    )


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
        paper_skeleton=_fresh_paper_skeleton_text(cwd, state),
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


def _read_optional_text(path: str | Path | None) -> str | None:
    if not path or not Path(path).exists():
        return None
    return read_text(path)


def _fresh_paper_skeleton_text(cwd: str | Path | None, state: SessionState) -> str | None:
    if not state.artifacts.paper_skeleton_md:
        return None
    status = paper_skeleton_status(cwd)
    if status.get("status") == "pass":
        return _read_optional_text(state.artifacts.paper_skeleton_md)
    if status.get("status") == "missing":
        return None
    raise ContractError(
        "Recorded paper-skeleton.md is not fresh enough for drafting. "
        f"Status: {status.get('status')}; reason: {status.get('reason') or status.get('detail') or 'unknown'}."
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
