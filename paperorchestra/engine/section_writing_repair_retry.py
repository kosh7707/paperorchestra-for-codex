from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import extract_latex
from paperorchestra.engine.citation_coverage import _ensure_minimum_citation_coverage
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode
from paperorchestra.engine.latex_postprocess import _stabilize_figure_float_placement
from paperorchestra.engine.plot_stages import _inject_missing_plot_assets
from paperorchestra.engine.reports import _blocking_issues
from paperorchestra.engine.section_writing_repair_notes import citation_alias_note, dropped_citation_note
from paperorchestra.engine.section_writing_repair_prompt import build_section_repair_retry_prompt
from paperorchestra.engine.section_writing_repair_types import SectionRepairResult
from paperorchestra.engine.section_writing_support import (
    SectionDraftContext,
    SectionValidationContext,
    normalize_section_draft,
    validate_section_draft,
)
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.structure import _canonical_generated_section_title
from paperorchestra.runtime.provider_base import BaseProvider


def repair_retry_draft(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    user_prompt: str,
    latex: str,
    blocking_issues: list[Any],
    draft_context: SectionDraftContext,
    validation_context: SectionValidationContext,
    min_citation_coverage: int,
    citation_map: dict[str, Any],
    plot_assets_index: dict[str, Any],
    selected_sections: list[str],
    strict_claim_safe_prompt: bool,
    citation_replacements: dict[str, str],
    lane_notes: list[str],
) -> SectionRepairResult | None:
    repair_prompt = build_section_repair_retry_prompt(
        user_prompt=user_prompt,
        latex=latex,
        blocking_issues=blocking_issues,
        min_citation_coverage=min_citation_coverage,
    )
    retry_response, retry_lane_type, retry_fallback_used, retry_lane_notes = _complete_with_runtime_mode(
        _build_completion_request(
            system_prompt=PROMPTS.render_section_writer_system(),
            user_prompt=repair_prompt,
        ),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="ralph",
        trace_stage="section_writing_repair",
    )
    retry_latex = extract_latex(retry_response)
    retry_latex, retry_replacements, retry_dropped_citations = normalize_section_draft(
        retry_latex,
        draft_context,
    )
    retry_issues = validate_section_draft(retry_latex, validation_context)
    retry_blocking = _blocking_issues(retry_issues)

    retry_codes = {issue.code for issue in retry_blocking}
    can_bridge_citations = retry_blocking and retry_codes <= {"citation_coverage_insufficient"}
    if can_bridge_citations and selected_sections:
        selected_titles = {_canonical_generated_section_title(section) for section in selected_sections}
        can_bridge_citations = bool(selected_titles & {"related work", "background and related work"})
    if can_bridge_citations:
        bridged_retry_latex = _ensure_minimum_citation_coverage(
            retry_latex,
            citation_map,
            target=min_citation_coverage,
        )
        if bridged_retry_latex != retry_latex:
            retry_latex = bridged_retry_latex
            retry_issues = validate_section_draft(retry_latex, validation_context)
            retry_blocking = _blocking_issues(retry_issues)

    if not retry_blocking:
        result_notes = list(lane_notes) + [
            "Section writer draft was retried after section-contract validation failure."
        ] + retry_lane_notes
        if citation_replacements:
            result_notes.append(
                citation_alias_note("Canonicalized citation-key aliases in section draft", citation_replacements)
            )
        if retry_replacements:
            result_notes.append(
                citation_alias_note("Canonicalized citation-key aliases in section retry draft", retry_replacements)
            )
        if retry_dropped_citations:
            result_notes.append(
                dropped_citation_note(
                    strict_claim_safe_prompt=strict_claim_safe_prompt,
                    retry=True,
                    dropped_citations=retry_dropped_citations,
                )
            )
        return SectionRepairResult(
            latex=retry_latex,
            validation_issues=retry_issues,
            blocking_issues=[],
            lane_notes=result_notes,
            lane_type=retry_lane_type,
            fallback_used=retry_fallback_used,
        )

    if not any(issue.code == "plot_plan_not_reflected" for issue in retry_blocking):
        return None
    repaired_retry_latex = _inject_missing_plot_assets(retry_latex, retry_blocking, plot_assets_index)
    repaired_retry_latex = _stabilize_figure_float_placement(repaired_retry_latex)
    sanitized_issues = validate_section_draft(repaired_retry_latex, validation_context)
    if _blocking_issues(sanitized_issues):
        return None
    return SectionRepairResult(
        latex=repaired_retry_latex,
        validation_issues=sanitized_issues,
        blocking_issues=[],
        lane_notes=list(lane_notes)
        + [
            (
                "Section retry draft received deterministic post-processing for residual "
                "plot-plan/numeric validation issues."
            )
        ]
        + retry_lane_notes,
        lane_type=retry_lane_type,
        fallback_used=retry_fallback_used,
    )
