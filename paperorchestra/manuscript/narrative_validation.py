from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.narrative_coverage import _narrative_item_covered, _narrative_terms_from_item
from paperorchestra.manuscript.narrative_role_checks import _narrative_role_issues, _story_beat_issue
from paperorchestra.manuscript.validation_types import ValidationIssue


def check_narrative_section_roles(latex: str, narrative_plan: dict[str, Any] | None) -> list[ValidationIssue]:
    if not isinstance(narrative_plan, dict):
        return []
    issues: list[ValidationIssue] = []
    for role in narrative_plan.get("section_roles") or []:
        if isinstance(role, dict):
            issues.extend(_narrative_role_issues(latex, role))
    for beat in narrative_plan.get("story_beats") or []:
        if isinstance(beat, dict):
            issue = _story_beat_issue(latex, beat)
            if issue is not None:
                issues.append(issue)
    return issues


__all__ = ["_narrative_item_covered", "_narrative_terms_from_item", "check_narrative_section_roles"]
