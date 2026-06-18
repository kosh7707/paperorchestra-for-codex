from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from paperorchestra.engine.citation_coverage import _ensure_minimum_citation_coverage
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode
from paperorchestra.engine.intro_related_draft import IntroRelatedDraft, draft_from_intro_related_response
from paperorchestra.engine.intro_related_prompt import IntroRelatedPromptPlan
from paperorchestra.engine.intro_related_support import (
    INTRO_RELATED_REPAIRABLE_CODES,
    append_citation_replacement_note,
    append_dropped_citation_note,
    blocking_issue_codes,
    make_intro_related_contexts,
    validate_intro_related_latex,
)
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text
from paperorchestra.engine.reports import _blocking_issues
from paperorchestra.runtime.provider_base import BaseProvider

DECIMAL_GROUNDING_REPAIR_INSTRUCTION = (
    "- Every decimal or percent value in the LaTeX must appear verbatim in project_experimental_log. "
    "If a number is not grounded there, remove it or rewrite the sentence qualitatively "
    "without introducing a replacement number."
)


def _repair_prompt(plan: IntroRelatedPromptPlan, draft: IntroRelatedDraft) -> str:
    blocking_issues = _blocking_issues(draft.validation_issues)
    return f"""
{plan.user_prompt}

{_data_block('current_intro_related_draft.tex', _prompt_compact_text(draft.latex, head_chars=12000, tail_chars=2000))}

{_data_block(
    'validation_issues.json',
    json.dumps([issue.to_dict() for issue in blocking_issues], indent=2, ensure_ascii=False),
)}

Repair Instructions:
- Revise the existing Introduction/Related Work draft to satisfy the exact validation issues above.
- Use ONLY citation keys from citation_checklist.
- Increase citation coverage until it satisfies min_cite_paper_count.
{DECIMAL_GROUNDING_REPAIR_INSTRUCTION}
- Preserve valid existing prose where possible and return LaTeX only.
""".strip()


def repair_intro_related_draft(
    cwd: str | Path | None,
    provider: BaseProvider,
    plan: IntroRelatedPromptPlan,
    draft: IntroRelatedDraft,
    *,
    runtime_mode: str,
    max_attempts: int = 2,
) -> IntroRelatedDraft:
    repairable_codes = blocking_issue_codes(draft.validation_issues)
    if not repairable_codes or not repairable_codes <= INTRO_RELATED_REPAIRABLE_CODES:
        return draft

    current = draft
    for repair_attempt in range(1, max_attempts + 1):
        if not _blocking_issues(current.validation_issues):
            break
        retry_response, retry_lane_type, retry_fallback_used, retry_lane_notes = _complete_with_runtime_mode(
            _build_completion_request(
                system_prompt=plan.system_prompt,
                user_prompt=_repair_prompt(plan, current),
            ),
            provider=provider,
            runtime_mode=runtime_mode,
            cwd=cwd,
            omx_lane_type="ralph",
            trace_stage="intro_related_repair" if repair_attempt == 1 else f"intro_related_repair_{repair_attempt}",
        )
        lane_notes = list(current.lane_notes)
        lane_notes.append(
            "Introduction/Related Work draft repair attempt "
            f"{repair_attempt} ran after citation-contract validation failure."
        )
        lane_notes.extend(retry_lane_notes)
        if current.initial_citation_replacements and repair_attempt == 1:
            append_citation_replacement_note(
                lane_notes,
                current.initial_citation_replacements,
                label="Introduction/Related Work draft",
            )

        retry_draft = draft_from_intro_related_response(
            retry_response,
            lane_type=retry_lane_type,
            fallback_used=retry_fallback_used,
            lane_notes=lane_notes,
            plan=plan,
            repair_attempts=repair_attempt,
            initial_citation_replacements=current.initial_citation_replacements,
            initial_dropped_citations=current.initial_dropped_citations,
        )
        if retry_draft.current_citation_replacements:
            append_citation_replacement_note(
                retry_draft.lane_notes,
                retry_draft.current_citation_replacements,
                label=f"Introduction/Related Work repair attempt {repair_attempt}",
            )
        append_dropped_citation_note(
            retry_draft.lane_notes,
            retry_draft.current_dropped_citations,
            strict_claim_safe_prompt=plan.strict_claim_safe_prompt,
            label=f"Introduction/Related Work repair attempt {repair_attempt}",
        )
        current = retry_draft
        if not _blocking_issues(current.validation_issues):
            break
        if blocking_issue_codes(current.validation_issues) - INTRO_RELATED_REPAIRABLE_CODES:
            break
    return current


def append_initial_intro_related_notes(plan: IntroRelatedPromptPlan, draft: IntroRelatedDraft) -> IntroRelatedDraft:
    lane_notes = list(draft.lane_notes)
    if draft.repair_attempts == 0:
        append_citation_replacement_note(
            lane_notes,
            draft.initial_citation_replacements,
            label="Introduction/Related Work draft",
        )
    append_dropped_citation_note(
        lane_notes,
        draft.initial_dropped_citations,
        strict_claim_safe_prompt=plan.strict_claim_safe_prompt,
        label="Introduction/Related Work draft",
    )
    return replace(draft, lane_notes=lane_notes)


def bridge_intro_related_citation_coverage(draft: IntroRelatedDraft, plan: IntroRelatedPromptPlan) -> IntroRelatedDraft:
    if not blocking_issue_codes(draft.validation_issues) <= {"citation_coverage_insufficient"}:
        return draft
    bridged_latex = _ensure_minimum_citation_coverage(
        draft.latex,
        plan.citation_map,
        target=plan.min_citation_coverage,
    )
    if bridged_latex == draft.latex:
        return draft
    _, validation_context = make_intro_related_contexts(plan)
    validation_issues = validate_intro_related_latex(bridged_latex, validation_context)
    return replace(
        draft,
        latex=bridged_latex,
        validation_issues=validation_issues,
        lane_notes=draft.lane_notes
        + [
            "Added a bounded related-work citation bridge after repair attempts left "
            "only a small citation-coverage shortfall."
        ],
    )
