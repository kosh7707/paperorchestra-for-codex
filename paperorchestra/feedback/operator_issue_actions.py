from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_issue_constants import OPERATOR_SOURCE


def _action_for_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_id": f"operator-feedback:{issue['id']}",
        "code": "operator_feedback_issue",
        "automation": "semi_auto",
        "source_issue_id": issue["id"],
        "target_section": issue["target_section"],
        "authority_class": issue["authority_class"],
        "owner_category": issue["owner_category"],
        "reason": issue["rationale"],
        "suggested_action": issue["suggested_action"],
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
    }
