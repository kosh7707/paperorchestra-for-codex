from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.engine.latex_postprocess import _drop_unknown_citation_keys
from paperorchestra.engine.prompt_context import _source_grounding_text, _unknown_citation_key_counts
from paperorchestra.engine.reports import _blocking_issues, collect_paper_contract_issues
from paperorchestra.engine.section_scope import _preserve_all_except_sections
from paperorchestra.engine.intro_related_prompt import IntroRelatedPromptPlan
from paperorchestra.manuscript.repair import _remove_material_packet_sections, _sanitize_manuscript_control_prose
from paperorchestra.manuscript.citations import canonicalize_citation_keys

INTRO_RELATED_REPAIRABLE_CODES = {
    "unknown_citation_keys",
    "citation_coverage_insufficient",
    "numeric_grounding_mismatch",
}
INTRO_RELATED_SECTION_NAMES = ["Introduction", "Related Work"]


@dataclass(frozen=True)
class IntroRelatedDraftContext:
    template: str
    citation_map: dict[str, Any]
    strict_claim_safe_prompt: bool


@dataclass(frozen=True)
class IntroRelatedValidationContext:
    inputs: dict[str, str]
    citation_map: dict[str, Any]
    narrative_plan: dict[str, Any]
    claim_map: dict[str, Any]
    citation_placement_plan: dict[str, Any]


def normalize_intro_related_latex(
    latex: str,
    context: IntroRelatedDraftContext,
) -> tuple[str, dict[str, str], dict[str, int]]:
    latex = _preserve_all_except_sections(
        latex,
        context.template,
        rewritten_section_names=INTRO_RELATED_SECTION_NAMES,
    )
    latex = _remove_material_packet_sections(latex)
    latex = _sanitize_manuscript_control_prose(latex)
    latex, citation_replacements = canonicalize_citation_keys(latex, context.citation_map)
    if context.strict_claim_safe_prompt:
        dropped_citations = _unknown_citation_key_counts(latex, context.citation_map)
    else:
        latex, dropped_citations = _drop_unknown_citation_keys(latex, context.citation_map)
    return latex, citation_replacements, dropped_citations


def validate_intro_related_latex(latex: str, context: IntroRelatedValidationContext) -> list[Any]:
    return collect_paper_contract_issues(
        latex,
        citation_map=context.citation_map,
        figures_dir=None,
        plot_manifest=None,
        experimental_log_text=_source_grounding_text(context.inputs),
        narrative_plan=context.narrative_plan,
        claim_map=context.claim_map,
        citation_placement_plan=context.citation_placement_plan,
    )


def blocking_issue_codes(validation_issues: list[Any]) -> set[str]:
    return {issue.code for issue in _blocking_issues(validation_issues)}


def append_citation_replacement_note(
    notes: list[str],
    replacements: dict[str, str],
    *,
    label: str,
) -> None:
    if replacements:
        notes.append(
            f"Canonicalized citation-key aliases in {label}: "
            + ", ".join(f"{src}->{dst}" for src, dst in sorted(replacements.items()))
        )


def append_dropped_citation_note(
    notes: list[str],
    dropped_citations: dict[str, int],
    *,
    strict_claim_safe_prompt: bool,
    label: str,
) -> None:
    if not dropped_citations:
        return
    note_prefix = (
        f"Blocked unsupported citation keys in strict {label}: "
        if strict_claim_safe_prompt
        else f"Dropped unsupported citation keys in {label}: "
    )
    notes.append(note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items())))


def make_intro_related_contexts(
    plan: IntroRelatedPromptPlan,
) -> tuple[IntroRelatedDraftContext, IntroRelatedValidationContext]:
    return (
        IntroRelatedDraftContext(
            template=plan.inputs["template"],
            citation_map=plan.citation_map,
            strict_claim_safe_prompt=plan.strict_claim_safe_prompt,
        ),
        IntroRelatedValidationContext(
            inputs=plan.inputs,
            citation_map=plan.citation_map,
            narrative_plan=plan.narrative_plan,
            claim_map=plan.claim_map,
            citation_placement_plan=plan.citation_placement_plan,
        ),
    )
