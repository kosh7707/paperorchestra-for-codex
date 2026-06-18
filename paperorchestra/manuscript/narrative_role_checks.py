from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.claim_text import _contains_unnegated_phrase, _section_visible_latex, _section_visible_text
from paperorchestra.manuscript.narrative_coverage import _narrative_item_covered
from paperorchestra.manuscript.sections import _substantive_text
from paperorchestra.manuscript.validation_types import ValidationIssue


def _narrative_role_issues(latex: str, role: dict[str, Any]) -> list[ValidationIssue]:
    title = str(role.get("section_title") or "")
    section_latex = _section_visible_latex(latex, title)
    section_text = _substantive_text(section_latex)
    return [
        *_missing_role_item_issues(section_text, title, role.get("coverage_requirements") or role.get("must_cover") or []),
        *_forbidden_role_claim_issues(section_latex, title, role.get("must_not_claim") or []),
    ]


def _story_beat_issue(latex: str, beat: dict[str, Any]) -> ValidationIssue | None:
    target = str(beat.get("target_section") or "")
    section_text = _section_visible_text(latex, target)
    if _narrative_item_covered(section_text, beat):
        return None
    return ValidationIssue(
        code="narrative_story_beat_missing",
        severity="error",
        message=f"Story beat is missing from target section {target}: {str(beat.get('beat'))[:120]}",
    )


def _missing_role_item_issues(section_text: str, title: str, role_items: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for item in role_items:
        if _narrative_item_covered(section_text, item):
            continue
        label = str(item.get("authorial_claim") if isinstance(item, dict) else item)[:120]
        issues.append(
            ValidationIssue(
                code="narrative_section_role_missing",
                severity="error",
                message=f"Section {title} does not cover required narrative role item: {label}",
            )
        )
    return issues


def _forbidden_role_claim_issues(section_latex: str, title: str, forbidden_items: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for forbidden in forbidden_items:
        if not _contains_unnegated_phrase(section_latex, str(forbidden)):
            continue
        issues.append(
            ValidationIssue(
                code="narrative_forbidden_claim_present",
                severity="error",
                message=f"Section {title} contains forbidden narrative claim: {forbidden}",
            )
        )
    return issues
