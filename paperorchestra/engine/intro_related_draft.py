from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.core.io import extract_latex
from paperorchestra.engine.intro_related_prompt import IntroRelatedPromptPlan
from paperorchestra.engine.intro_related_support import (
    make_intro_related_contexts,
    normalize_intro_related_latex,
    validate_intro_related_latex,
)


@dataclass(frozen=True)
class IntroRelatedDraft:
    latex: str
    validation_issues: list[Any]
    lane_type: str
    fallback_used: bool
    lane_notes: list[str]
    initial_citation_replacements: dict[str, str]
    initial_dropped_citations: dict[str, int]
    current_citation_replacements: dict[str, str]
    current_dropped_citations: dict[str, int]
    repair_attempts: int = 0


def draft_from_intro_related_response(
    response: str,
    *,
    lane_type: str,
    fallback_used: bool,
    lane_notes: list[str],
    plan: IntroRelatedPromptPlan,
    repair_attempts: int = 0,
    initial_citation_replacements: dict[str, str] | None = None,
    initial_dropped_citations: dict[str, int] | None = None,
) -> IntroRelatedDraft:
    draft_context, validation_context = make_intro_related_contexts(plan)
    latex = extract_latex(response)
    latex, citation_replacements, dropped_citations = normalize_intro_related_latex(latex, draft_context)
    validation_issues = validate_intro_related_latex(latex, validation_context)
    return IntroRelatedDraft(
        latex=latex,
        validation_issues=validation_issues,
        lane_type=lane_type,
        fallback_used=fallback_used,
        lane_notes=list(lane_notes),
        initial_citation_replacements=(
            initial_citation_replacements if initial_citation_replacements is not None else citation_replacements
        ),
        initial_dropped_citations=(
            initial_dropped_citations if initial_dropped_citations is not None else dropped_citations
        ),
        current_citation_replacements=citation_replacements,
        current_dropped_citations=dropped_citations,
        repair_attempts=repair_attempts,
    )
