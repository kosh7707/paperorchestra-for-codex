from __future__ import annotations

from typing import Any

from paperorchestra.feedback.candidate_approval import actionable_candidate_approval_role, candidate_approval_issues_for_role
from paperorchestra.feedback.operator_answer_metadata import (
    HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS,
    validate_operator_review_notes,
)
from paperorchestra.feedback.operator_contract import OPERATOR_FEEDBACK_SCHEMA_VERSION
from paperorchestra.feedback.operator_issue_contract import OPERATOR_SOURCE
from paperorchestra.feedback.operator_issue_draft import normalize_operator_issue_draft
from paperorchestra.core.errors import ContractError


def _attach_operator_review_notes(feedback: dict[str, Any], draft: dict[str, Any]) -> None:
    operator_review_notes = None
    if "operator_review_notes" in draft:
        operator_review_notes = validate_operator_review_notes(draft.get("operator_review_notes"))

    human_needed_answer = draft.get("human_needed_answer")
    if isinstance(human_needed_answer, dict):
        schema_version = human_needed_answer.get("schema_version")
        if schema_version in HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS:
            feedback["human_needed_answer"] = dict(human_needed_answer)
        elif "schema_version" in human_needed_answer:
            raise ContractError("human_needed_answer metadata has an unsupported schema_version")
        else:
            migrated_notes = validate_operator_review_notes(human_needed_answer)
            if operator_review_notes is None:
                operator_review_notes = migrated_notes
    if operator_review_notes is not None:
        feedback["operator_review_notes"] = operator_review_notes


def normalize_operator_feedback_draft(packet: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    approval_role = actionable_candidate_approval_role(packet)
    intent, issues = normalize_operator_issue_draft(
        packet_sha256=packet["packet_sha256"],
        draft=draft,
        approval_role=approval_role,
    )
    feedback = {
        "schema_version": OPERATOR_FEEDBACK_SCHEMA_VERSION,
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "intent": intent,
        "packet_sha256": packet["packet_sha256"],
        "manuscript_sha256": packet["manuscript_sha256"],
        "issues": issues,
    }
    if isinstance(draft.get("rendered_pdf_no_issues"), dict):
        feedback["rendered_pdf_no_issues"] = dict(draft["rendered_pdf_no_issues"])
    _attach_operator_review_notes(feedback, draft)
    return feedback


__all__ = [
    "actionable_candidate_approval_role",
    "candidate_approval_issues_for_role",
    "normalize_operator_feedback_draft",
]
