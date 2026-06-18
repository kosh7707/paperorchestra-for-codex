from __future__ import annotations

import re
from typing import Any

from paperorchestra.core.boundary import normalized_coverage_groups
from paperorchestra.manuscript.claim_coverage import _terms_nearby
from paperorchestra.manuscript.claim_text import _contains_unnegated_phrase, _section_visible_latex, _section_visible_text
from paperorchestra.manuscript.sections import _substantive_text
from paperorchestra.manuscript.validation_types import ValidationIssue


def _narrative_terms_from_item(item: Any) -> list[str]:
    if isinstance(item, dict):
        groups = normalized_coverage_groups(item)
        terms = [term for group in groups for term in group]
        if terms:
            return terms[:8]
        text = str(item.get("authorial_claim") or item.get("beat") or item.get("text") or "")
    else:
        text = str(item)
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{3,}", text)[:6]


def _narrative_item_covered(section_text: str, item: Any) -> bool:
    if isinstance(item, dict) and item.get("coverage_groups"):
        for group in normalized_coverage_groups(item):
            terms = [str(term) for term in group if str(term).strip()]
            if terms and _terms_nearby(section_text, terms):
                return True
        return False
    terms = _narrative_terms_from_item(item)
    return not terms or any(term.lower() in section_text.lower() for term in terms)


def check_narrative_section_roles(latex: str, narrative_plan: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(narrative_plan, dict):
        return []
    issues: list[ValidationIssue] = []
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        title = str(role.get("section_title") or "")
        section_latex = _section_visible_latex(latex, title)
        section_text = _substantive_text(section_latex)
        role_items = role.get("coverage_requirements") or role.get("must_cover") or []
        for item in role_items:
            if not _narrative_item_covered(section_text, item):
                label = str(item.get("authorial_claim") if isinstance(item, dict) else item)[:120]
                issues.append(
                    ValidationIssue(
                        code="narrative_section_role_missing",
                        severity="error",
                        message=f"Section {title} does not cover required narrative role item: {label}",
                    )
                )
        for forbidden in role.get("must_not_claim") or []:
            if _contains_unnegated_phrase(section_latex, str(forbidden)):
                issues.append(
                    ValidationIssue(
                        code="narrative_forbidden_claim_present",
                        severity="error",
                        message=f"Section {title} contains forbidden narrative claim: {forbidden}",
                    )
                )
    for beat in narrative_plan.get("story_beats") or []:
        if not isinstance(beat, dict):
            continue
        target = str(beat.get("target_section") or "")
        section_text = _section_visible_text(latex, target)
        if not _narrative_item_covered(section_text, beat):
            issues.append(
                ValidationIssue(
                    code="narrative_story_beat_missing",
                    severity="error",
                    message=f"Story beat is missing from target section {target}: {str(beat.get('beat'))[:120]}",
                )
            )
    return issues
