from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.engine.latex_postprocess import (
    _drop_unknown_citation_keys,
    _ensure_bibliography_hook,
    _ensure_generated_plot_usage,
    _normalize_generated_plot_paths,
    _normalize_source_figure_paths,
    _stabilize_figure_float_placement,
)
from paperorchestra.engine.prompt_context import _source_grounding_text, _unknown_citation_key_counts
from paperorchestra.engine.reports import collect_paper_contract_issues
from paperorchestra.engine.section_scope import (
    _filter_section_scoped_issues,
    _preserve_all_except_sections,
    _preserve_existing_sections,
    _selected_section_template,
)
from paperorchestra.manuscript.repair import (
    _ensure_discussion_section_for_claim_boundaries,
    _ensure_required_claim_scope_notes,
    _remove_material_packet_sections,
    _restore_missing_referenced_labels,
)
from paperorchestra.manuscript.validator import canonicalize_citation_keys


SECTION_REPAIRABLE_CODES = {
    "unknown_citation_keys",
    "citation_coverage_insufficient",
    "numeric_grounding_mismatch",
    "plot_plan_not_reflected",
    "expected_section_missing",
    "expected_section_too_shallow",
    "required_claim_missing",
    "required_claim_keyword_stuffing",
    "narrative_section_role_missing",
}


@dataclass(frozen=True)
class SectionDraftContext:
    current_source: str | None
    selected_sections: list[str] | None
    intro_related_source: str | None
    template_content: str
    citation_map: dict[str, Any]
    plot_assets_index: dict[str, Any]
    figures_dir: str | Path | None
    claim_map: dict[str, Any]
    strict_claim_safe_prompt: bool


@dataclass(frozen=True)
class SectionValidationContext:
    selected_sections: list[str] | None
    citation_map: dict[str, Any]
    figures_dir: str | Path | None
    plot_manifest: dict[str, Any]
    plot_assets_index: dict[str, Any]
    inputs: dict[str, str]
    expected_section_titles: list[str]
    narrative_plan: dict[str, Any]
    claim_map: dict[str, Any]
    citation_placement_plan: dict[str, Any]


def normalize_section_draft(latex: str, context: SectionDraftContext) -> tuple[str, dict[str, str], dict[str, int]]:
    if context.selected_sections and context.current_source is not None:
        latex = _preserve_all_except_sections(
            latex,
            context.current_source,
            rewritten_section_names=context.selected_sections,
        )
    elif context.intro_related_source:
        latex = _preserve_existing_sections(
            latex,
            context.intro_related_source,
            section_names=["Introduction", "Related Work"],
        )
    latex = _restore_missing_referenced_labels(latex, context.template_content)
    latex = _ensure_bibliography_hook(latex, context.citation_map)
    latex = _normalize_generated_plot_paths(latex, context.plot_assets_index)
    latex = _normalize_source_figure_paths(latex, context.figures_dir)
    latex = _ensure_generated_plot_usage(latex, context.plot_assets_index)
    latex = _stabilize_figure_float_placement(latex)
    latex = _remove_material_packet_sections(latex)
    latex = _ensure_discussion_section_for_claim_boundaries(latex, context.claim_map)
    latex = _ensure_required_claim_scope_notes(latex, context.claim_map)
    latex, citation_replacements = canonicalize_citation_keys(latex, context.citation_map)
    if context.strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, context.citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, context.citation_map)
    return latex, citation_replacements, dropped_citations


def validate_section_draft(latex: str, context: SectionValidationContext) -> list[Any]:
    validation_subject = (
        _selected_section_template(latex, context.selected_sections)
        if context.selected_sections
        else latex
    )
    issues = collect_paper_contract_issues(
        validation_subject,
        citation_map=context.citation_map,
        figures_dir=context.figures_dir,
        plot_manifest=context.plot_manifest,
        plot_assets_index=context.plot_assets_index,
        experimental_log_text=_source_grounding_text(context.inputs),
        expected_section_titles=context.expected_section_titles,
        narrative_plan=context.narrative_plan,
        claim_map=context.claim_map,
        citation_placement_plan=context.citation_placement_plan,
    )
    return _filter_section_scoped_issues(issues, selected_sections=context.selected_sections)
