from __future__ import annotations

from typing import Any

_APPROVAL_ARTIFACT_ROLES = {"qa_loop_execution", "operator_feedback_execution"}


def candidate_approval_issues_for_role(issues: list[dict[str, Any]], approval_role: str | None) -> list[dict[str, Any]]:
    """Return only the approval-target issues for an approve-existing request."""

    if approval_role not in _APPROVAL_ARTIFACT_ROLES:
        return []
    return [issue for issue in issues if isinstance(issue, dict) and issue.get("source_artifact_role") == approval_role]
