from __future__ import annotations

from pathlib import Path
from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, read_text
from paperorchestra.core.models import SessionState
from paperorchestra.engine.citation_coverage import _citation_coverage_target
from paperorchestra.engine.latex_postprocess import (
    _filter_plot_context_for_latex,
    _reviewable_plot_assets_index,
    _reviewable_plot_manifest,
)
from paperorchestra.engine.planning_stages import (
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _compact_outline_for_prompt,
    _compact_plot_assets_for_prompt,
    _compact_plot_manifest_for_prompt,
    _prompt_compact_text,
    _raise_if_strict_source_citations_unmapped,
    _read_inputs,
    _source_critical_context_for_prompt,
    _strict_content_gates_enabled,
)
from paperorchestra.engine.section_scope import (
    _expected_section_titles_from_outline,
    _filtered_outline_for_sections,
    _preserve_existing_sections,
    _resolve_selected_sections,
    _selected_section_template,
)
from paperorchestra.engine.section_writing_types import (
    CitationPromptContext,
    OutlinePromptContext,
    PlanningPromptPayloads,
    PlotPromptContext,
    SectionPromptContext,
    TemplatePromptContext,
)
from paperorchestra.manuscript.repair import _citation_map_for_selected_sections


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


def _outline_context(state: SessionState, selected_sections: list[str]) -> OutlinePromptContext:
    outline = read_json(state.artifacts.outline_json)
    raw_prompt_outline = _filtered_outline_for_sections(outline, selected_sections) if selected_sections else outline
    expected_section_titles = selected_sections if selected_sections else _expected_section_titles_from_outline(outline)
    return OutlinePromptContext(
        outline=outline,
        prompt_outline=_compact_outline_for_prompt(raw_prompt_outline),
        expected_section_titles=expected_section_titles,
    )


def _citation_context(
    state: SessionState,
    *,
    current_source: str | None,
    selected_sections: list[str],
    strict_claim_safe_prompt: bool,
) -> CitationPromptContext:
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_citation_map = (
        _citation_map_for_selected_sections(current_source, citation_map, selected_sections)
        if current_source is not None
        else citation_map
    )
    return CitationPromptContext(
        citation_map=citation_map,
        prompt_citation_map=_compact_citation_map_for_prompt(
            prompt_citation_map,
            include_abstract=strict_claim_safe_prompt,
            include_authors=False,
            include_year=strict_claim_safe_prompt,
            include_venue=strict_claim_safe_prompt,
            include_provenance=False,
            include_origin=False,
            include_matched_query=False,
        ),
        min_citation_coverage=_citation_coverage_target(citation_map),
    )


def _plot_context(
    state: SessionState,
    *,
    selected_sections: list[str],
    selected_section_source: str | None,
) -> PlotPromptContext:
    raw_plot_manifest = (
        read_json(state.artifacts.plot_manifest_json)
        if state.artifacts.plot_manifest_json
        else {"figures": []}
    )
    raw_plot_assets_index = (
        read_json(state.artifacts.plot_assets_json)
        if state.artifacts.plot_assets_json
        else {"assets": []}
    )
    plot_assets_index = _reviewable_plot_assets_index(raw_plot_assets_index)
    plot_manifest = _reviewable_plot_manifest(raw_plot_manifest, raw_plot_assets_index)
    scoped_plot_manifest, scoped_plot_assets_index = (
        _filter_plot_context_for_latex(selected_section_source, plot_manifest, plot_assets_index)
        if selected_sections
        else (plot_manifest, plot_assets_index)
    )
    return PlotPromptContext(
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
        scoped_plot_manifest=scoped_plot_manifest,
        scoped_plot_assets_index=scoped_plot_assets_index,
        prompt_plot_manifest=_compact_plot_manifest_for_prompt(scoped_plot_manifest),
        prompt_plot_assets_index=_compact_plot_assets_for_prompt(scoped_plot_assets_index),
    )


def _template_context(
    state: SessionState,
    *,
    current_source: str | None,
    selected_sections: list[str],
) -> TemplatePromptContext:
    intro_related_source = None
    if current_source is not None:
        template_content = _selected_section_template(current_source, selected_sections)
    else:
        template_content = read_text(state.inputs.template_path)
        if state.artifacts.intro_related_tex and Path(state.artifacts.intro_related_tex).exists():
            intro_related_source = read_text(state.artifacts.intro_related_tex)
            template_content = _preserve_existing_sections(
                template_content,
                intro_related_source,
                section_names=["Introduction", "Related Work"],
            )
    return TemplatePromptContext(
        template_content=template_content,
        intro_related_source=intro_related_source,
        prompt_template_content=_prompt_compact_text(template_content, head_chars=5000, tail_chars=1000),
    )
