from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import extract_latex
from paperorchestra.engine.citation_coverage import _ensure_minimum_citation_coverage
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode
from paperorchestra.engine.latex_postprocess import _stabilize_figure_float_placement
from paperorchestra.engine.plot_stages import _inject_missing_plot_assets
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text
from paperorchestra.engine.reports import _blocking_issues
from paperorchestra.engine.section_writing_support import (
    SectionDraftContext,
    SectionValidationContext,
    normalize_section_draft,
    validate_section_draft,
)
from paperorchestra.manuscript.prompts import PROMPTS
from paperorchestra.manuscript.structure import _canonical_generated_section_title
from paperorchestra.runtime.providers import BaseProvider


@dataclass(frozen=True)
class SectionRepairResult:
    latex: str
    validation_issues: list[Any]
    blocking_issues: list[Any]
    lane_notes: list[str]
    lane_type: str
    fallback_used: bool


def citation_alias_note(prefix: str, replacements: dict[str, str]) -> str:
    return prefix + ": " + ", ".join(f"{src}->{dst}" for src, dst in sorted(replacements.items()))


def dropped_citation_note(*, strict_claim_safe_prompt: bool, retry: bool, dropped_citations: dict[str, int]) -> str:
    action = "Blocked" if strict_claim_safe_prompt else "Dropped"
    strict = "strict " if strict_claim_safe_prompt else ""
    retry_label = "retry " if retry else ""
    note_prefix = f"{action} unsupported citation keys in {strict}section {retry_label}draft: "
    return note_prefix + ", ".join(f"{key}({count})" for key, count in sorted(dropped_citations.items()))


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
    repair_prompt = f"""
{user_prompt}

{_data_block('current_draft.tex', _prompt_compact_text(latex, head_chars=10000, tail_chars=2000))}

{_data_block(
    'validation_issues.json',
    json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False),
)}

Repair Instructions:
- Revise the existing manuscript draft to satisfy the validation issues above.
- Use ONLY citation keys from the verified reference library.
- Increase citation coverage until the paper satisfies the citation coverage contract, using at least {min_citation_coverage} distinct verified citations when that many are available.
- Every decimal or percent value in the manuscript must appear verbatim in the measurement log. If a number is not grounded there, remove it or rewrite the claim qualitatively without introducing a replacement number.
- Ensure every required plot-plan figure is represented in the manuscript. Use available generated plot assets/snippets instead of inventing new figure files.
- Cover every required claim and narrative role item in its target section with meaningful, section-local prose rather than keyword stuffing.
- Expand every missing or shallow expected section with grounded, section-specific substance from the technical context, measurement log, section plan, and current template.
- Do not leave Method, Security Analysis, Implementation/Results, Discussion, or Conclusion as heading-only placeholders.
- Do not preserve input-note headings as manuscript sections; fold their constraints into Discussion and normal authorial prose.
- Preserve valid existing structure, plot usage, and grounded claims where possible.
- Do NOT invent meta sections such as checklists or workflow notes that are not part of the manuscript template.
- When rewrite_scope.json lists only_sections, preserve the existing section titles, citation keys, and figure references already present in current_template.tex.
- Return LaTeX only.
""".strip()
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
