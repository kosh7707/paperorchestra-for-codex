from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.engine.section_writing_support import SectionDraftContext, SectionValidationContext


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


@dataclass(frozen=True)
class PlanningPromptPayloads:
    narrative_plan: dict[str, Any]
    claim_map: dict[str, Any]
    citation_placement_plan: dict[str, Any]
    writer_brief: dict[str, Any]


@dataclass(frozen=True)
class OutlinePromptContext:
    outline: dict[str, Any]
    prompt_outline: dict[str, Any]
    expected_section_titles: list[str]


@dataclass(frozen=True)
class CitationPromptContext:
    citation_map: dict[str, Any]
    prompt_citation_map: dict[str, Any]
    min_citation_coverage: int


@dataclass(frozen=True)
class PlotPromptContext:
    plot_manifest: dict[str, Any]
    plot_assets_index: dict[str, Any]
    scoped_plot_manifest: dict[str, Any]
    scoped_plot_assets_index: dict[str, Any]
    prompt_plot_manifest: dict[str, Any]
    prompt_plot_assets_index: dict[str, Any]


@dataclass(frozen=True)
class TemplatePromptContext:
    template_content: str
    intro_related_source: str | None
    prompt_template_content: str


@dataclass(frozen=True)
class SectionPromptContext:
    selected_sections: list[str]
    current_source: str | None
    paper_skeleton: str | None
    planning: PlanningPromptPayloads
    outline: OutlinePromptContext
    citations: CitationPromptContext
    plots: PlotPromptContext
    template: TemplatePromptContext
    inputs: dict[str, str]
    source_critical_context: dict[str, Any]
    figures_dir: str | None
    strict_claim_safe_prompt: bool
