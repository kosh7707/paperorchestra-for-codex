from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    _author_facing_writer_brief_block,
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _writer_brief_from_planning,
)
from paperorchestra.engine.prompt_context import (
    _compact_citation_map_for_prompt,
    _compact_outline_for_prompt,
    _compact_plot_assets_for_prompt,
    _compact_plot_manifest_for_prompt,
    _data_block,
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
from paperorchestra.engine.section_writing_support import SectionDraftContext, SectionValidationContext
from paperorchestra.manuscript.repair import _citation_map_for_selected_sections
from paperorchestra.manuscript.validator import canonical_citation_keys


@dataclass(frozen=True)
class SectionWritingPlan:
    selected_sections: list[str]
    current_source: str | None
    citation_map: dict[str, Any]
    plot_assets_index: dict[str, Any]
    user_prompt: str
    draft_context: SectionDraftContext
    validation_context: SectionValidationContext
    min_citation_coverage: int
    strict_claim_safe_prompt: bool


def build_section_writing_plan(
    cwd: str | Path | None,
    state: SessionState,
    *,
    selected_sections: list[str],
    claim_safe: bool,
) -> SectionWritingPlan:
    if selected_sections and not state.artifacts.paper_full_tex:
        raise ContractError("Need an existing paper.full.tex before rewriting only selected sections.")

    current_source = (
        read_text(state.artifacts.paper_full_tex)
        if selected_sections and state.artifacts.paper_full_tex
        else None
    )
    if current_source is not None:
        selected_sections = _resolve_selected_sections(current_source, selected_sections)

    narrative_plan, claim_map, citation_placement_plan = _planning_payloads_for_prompt(cwd)
    narrative_plan, claim_map, citation_placement_plan = _filter_planning_payloads_for_sections(
        narrative_plan,
        claim_map,
        citation_placement_plan,
        selected_sections,
    )
    writer_brief = _writer_brief_from_planning(narrative_plan, claim_map, citation_placement_plan)

    outline = read_json(state.artifacts.outline_json)
    raw_prompt_outline = _filtered_outline_for_sections(outline, selected_sections) if selected_sections else outline
    prompt_outline = _compact_outline_for_prompt(raw_prompt_outline)

    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    prompt_citation_map = (
        _citation_map_for_selected_sections(current_source, citation_map, selected_sections)
        if current_source is not None
        else citation_map
    )
    min_citation_coverage = _citation_coverage_target(citation_map)

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

    selected_section_source = (
        _selected_section_template(current_source, selected_sections)
        if selected_sections and current_source is not None
        else None
    )
    scoped_plot_manifest, scoped_plot_assets_index = (
        _filter_plot_context_for_latex(selected_section_source, plot_manifest, plot_assets_index)
        if selected_sections
        else (plot_manifest, plot_assets_index)
    )
    prompt_plot_manifest = _compact_plot_manifest_for_prompt(scoped_plot_manifest)
    prompt_plot_assets_index = _compact_plot_assets_for_prompt(scoped_plot_assets_index)
    expected_section_titles = selected_sections if selected_sections else _expected_section_titles_from_outline(outline)

    inputs = _read_inputs(state)
    strict_claim_safe_prompt = _strict_content_gates_enabled(claim_safe=claim_safe)
    _raise_if_strict_source_citations_unmapped(
        inputs,
        citation_map,
        stage="section_writing",
        strict_claim_safe=strict_claim_safe_prompt,
    )
    prompt_citation_map_compact = _compact_citation_map_for_prompt(
        prompt_citation_map,
        include_abstract=strict_claim_safe_prompt,
        include_authors=False,
        include_year=strict_claim_safe_prompt,
        include_venue=strict_claim_safe_prompt,
        include_provenance=False,
        include_origin=False,
        include_matched_query=False,
    )
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=3000, tail_chars=500)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=5000, tail_chars=1000)
    source_critical_context = _source_critical_context_for_prompt(inputs)
    figures_dir = state.inputs.figures_dir or ""

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

    draft_context = SectionDraftContext(
        current_source=current_source,
        selected_sections=selected_sections,
        intro_related_source=intro_related_source,
        template_content=template_content,
        citation_map=citation_map,
        plot_assets_index=plot_assets_index,
        figures_dir=state.inputs.figures_dir,
        claim_map=claim_map,
        strict_claim_safe_prompt=strict_claim_safe_prompt,
    )
    validation_context = SectionValidationContext(
        selected_sections=selected_sections,
        citation_map=citation_map,
        figures_dir=state.inputs.figures_dir,
        plot_manifest=scoped_plot_manifest if selected_sections else plot_manifest,
        plot_assets_index=scoped_plot_assets_index if selected_sections else plot_assets_index,
        inputs=inputs,
        expected_section_titles=expected_section_titles,
        narrative_plan=narrative_plan,
        claim_map=claim_map,
        citation_placement_plan=citation_placement_plan,
    )

    prompt_template_content = _prompt_compact_text(template_content, head_chars=5000, tail_chars=1000)
    section_scope_instructions = ""
    if selected_sections:
        section_scope_instructions = (
            "Section-scope Instructions:\n"
            f"- Rewrite ONLY these sections: {', '.join(selected_sections)}.\n"
            "- Preserve all section titles, labels, citations, and figure references already present in current_template.tex for those sections.\n"
            "- Do NOT invent new citation keys, figure filenames, labels, or cross-references that are absent from current_template.tex.\n"
            "- Prefer revising the prose within the existing section skeleton over introducing new structural elements.\n"
        )
    global_section_instructions = (
        "Global Writing Constraints:\n"
        f"- Use at least {min_citation_coverage} distinct verified citations when that many verified references are available.\n"
        "- Do NOT invent meta sections such as checklists or workflow notes that are not part of current_template.tex.\n"
        "- Write manuscript prose only; express evidence limits as scholarly assumptions, scope, and limitations.\n"
        "- Do NOT preserve input-note headings as manuscript sections; fold their constraints into normal prose, "
        "especially Discussion limitations.\n"
    )
    user_prompt = f"""
{_data_block('outline.json', json.dumps(prompt_outline, indent=2, ensure_ascii=False))}

{_author_facing_writer_brief_block(writer_brief)}

{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('source_critical_context.json', json.dumps(source_critical_context, indent=2, ensure_ascii=False))}

{_data_block('citation_map.json', json.dumps(prompt_citation_map_compact, indent=2, ensure_ascii=False))}

{_data_block('citation_coverage_target.json', json.dumps({
    'min_distinct_verified_citations': min_citation_coverage,
    'available_verified_citations': len(canonical_citation_keys(citation_map)),
}, ensure_ascii=False))}

{_data_block('plot_manifest.json', json.dumps(prompt_plot_manifest, indent=2, ensure_ascii=False))}

{_data_block('plot_assets.json', json.dumps(prompt_plot_assets_index, indent=2, ensure_ascii=False))}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('current_template.tex', prompt_template_content)}

{_data_block('figures_list', inputs['figures'])}

{_data_block('figures_dir', figures_dir or 'null')}
{_data_block('rewrite_scope.json', json.dumps({
    'only_sections': selected_sections,
    'preserve_all_other_sections': bool(selected_sections),
}, ensure_ascii=False))}

{global_section_instructions}
{section_scope_instructions}
""".strip()

    return SectionWritingPlan(
        selected_sections=selected_sections,
        current_source=current_source,
        citation_map=citation_map,
        plot_assets_index=plot_assets_index,
        user_prompt=user_prompt,
        draft_context=draft_context,
        validation_context=validation_context,
        min_citation_coverage=min_citation_coverage,
        strict_claim_safe_prompt=strict_claim_safe_prompt,
    )
