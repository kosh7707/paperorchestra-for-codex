from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.engine.section_writing_repair_retry import (
    SectionRepairResult,
    citation_alias_note,
    dropped_citation_note,
    repair_retry_draft,
)
from paperorchestra.engine.section_writing_support import SECTION_REPAIRABLE_CODES, SectionDraftContext, SectionValidationContext
from paperorchestra.runtime.provider_base import BaseProvider


def repair_section_draft_if_possible(
    *,
    cwd: str | Path | None,
    provider: BaseProvider,
    runtime_mode: str,
    user_prompt: str,
    latex: str,
    validation_issues: list[Any],
    blocking_issues: list[Any],
    draft_context: SectionDraftContext,
    validation_context: SectionValidationContext,
    min_citation_coverage: int,
    citation_map: dict[str, Any],
    plot_assets_index: dict[str, Any],
    selected_sections: list[str],
    strict_claim_safe_prompt: bool,
    citation_replacements: dict[str, str],
    dropped_citations: dict[str, int],
    lane_notes: list[str],
    lane_type: str,
    fallback_used: bool,
) -> SectionRepairResult:
    result = None
    result_notes = list(lane_notes)
    if blocking_issues and {issue.code for issue in blocking_issues} <= SECTION_REPAIRABLE_CODES:
        result = repair_retry_draft(
            cwd=cwd,
            provider=provider,
            runtime_mode=runtime_mode,
            user_prompt=user_prompt,
            latex=latex,
            blocking_issues=blocking_issues,
            draft_context=draft_context,
            validation_context=validation_context,
            min_citation_coverage=min_citation_coverage,
            citation_map=citation_map,
            plot_assets_index=plot_assets_index,
            selected_sections=selected_sections,
            strict_claim_safe_prompt=strict_claim_safe_prompt,
            citation_replacements=citation_replacements,
            lane_notes=result_notes,
        )
    elif citation_replacements:
        result_notes.append(citation_alias_note("Canonicalized citation-key aliases in section draft", citation_replacements))
    if result is not None:
        latex = result.latex
        validation_issues = result.validation_issues
        blocking_issues = result.blocking_issues
        result_notes = result.lane_notes
        lane_type = result.lane_type
        fallback_used = result.fallback_used
    if dropped_citations:
        result_notes.append(
            dropped_citation_note(
                strict_claim_safe_prompt=strict_claim_safe_prompt,
                retry=False,
                dropped_citations=dropped_citations,
            )
        )
    return SectionRepairResult(
        latex=latex,
        validation_issues=validation_issues,
        blocking_issues=blocking_issues,
        lane_notes=result_notes,
        lane_type=lane_type,
        fallback_used=fallback_used,
    )
