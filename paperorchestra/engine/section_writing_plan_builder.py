from __future__ import annotations

from pathlib import Path

from paperorchestra.core.models import SessionState
from paperorchestra.engine.section_writing_context import build_section_prompt_context
from paperorchestra.engine.section_writing_prompt_renderer import render_section_writing_user_prompt
from paperorchestra.engine.section_writing_support import SectionDraftContext, SectionValidationContext
from paperorchestra.engine.section_writing_types import SectionPromptContext, SectionWritingPlan


def build_section_writing_plan(
    cwd: str | Path | None,
    state: SessionState,
    *,
    selected_sections: list[str],
    claim_safe: bool,
) -> SectionWritingPlan:
    context = build_section_prompt_context(
        cwd,
        state,
        selected_sections=selected_sections,
        claim_safe=claim_safe,
    )
    return SectionWritingPlan(
        selected_sections=context.selected_sections,
        current_source=context.current_source,
        citation_map=context.citations.citation_map,
        plot_assets_index=context.plots.plot_assets_index,
        user_prompt=render_section_writing_user_prompt(context),
        draft_context=_draft_context(context),
        validation_context=_validation_context(context),
        min_citation_coverage=context.citations.min_citation_coverage,
        strict_claim_safe_prompt=context.strict_claim_safe_prompt,
    )


def _draft_context(context: SectionPromptContext) -> SectionDraftContext:
    return SectionDraftContext(
        current_source=context.current_source,
        selected_sections=context.selected_sections,
        intro_related_source=context.template.intro_related_source,
        template_content=context.template.template_content,
        citation_map=context.citations.citation_map,
        plot_assets_index=context.plots.plot_assets_index,
        figures_dir=context.figures_dir,
        claim_map=context.planning.claim_map,
        strict_claim_safe_prompt=context.strict_claim_safe_prompt,
    )


def _validation_context(context: SectionPromptContext) -> SectionValidationContext:
    return SectionValidationContext(
        selected_sections=context.selected_sections,
        citation_map=context.citations.citation_map,
        figures_dir=context.figures_dir,
        plot_manifest=context.plots.scoped_plot_manifest,
        plot_assets_index=context.plots.scoped_plot_assets_index,
        inputs=context.inputs,
        expected_section_titles=context.outline.expected_section_titles,
        narrative_plan=context.planning.narrative_plan,
        claim_map=context.planning.claim_map,
        citation_placement_plan=context.planning.citation_placement_plan,
    )
