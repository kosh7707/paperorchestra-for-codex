from __future__ import annotations

from typing import Any

from paperorchestra.feedback.candidate_approval_issues import candidate_approval_issues_for_role
from paperorchestra.feedback.operator_answer_metadata import OPERATOR_FEEDBACK_INTENTS
from paperorchestra.feedback.operator_issue_defaults import (
    _default_candidate_approval_issue,
    _default_missing_approval_issue,
    _fallback_human_needed_issue,
)
from paperorchestra.feedback.operator_issue_policy import (
    _cap_generated_issues,
    _infer_operator_issue_owner_category,
    _with_operator_issue_identity,
)


def _draft_intent(draft: dict[str, Any]) -> str:
    intent = str(draft.get("intent") or draft.get("primary_intent") or "").strip()
    if not intent and isinstance(draft.get("intents"), list):
        intent = next((str(item).strip() for item in draft["intents"] if str(item or "").strip()), "")
    if not intent:
        # A ready candidate in the packet is evidence that approval is possible,
        # not authority to approve it. Missing intent must continue through a
        # bounded operator-feedback candidate.
        intent = "generate_new_operator_candidate"
    if intent not in OPERATOR_FEEDBACK_INTENTS:
        raise ValueError(f"unsupported operator feedback intent: {intent}")
    return intent


def _normalized_draft_issues(draft: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "source_artifact_role",
        "source_item_key",
        "target_section",
        "severity",
        "rationale",
        "suggested_action",
        "authority_class",
        "owner_category",
    )
    issues: list[dict[str, Any]] = []
    for raw in draft.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        issue = {key: str(raw.get(key) or "").strip() for key in fields}
        if not issue["rationale"] or not issue["suggested_action"]:
            continue
        issue["owner_category"] = _infer_operator_issue_owner_category(issue)
        issues.append(issue)
    return issues


def _resolve_approval_request(
    intent: str,
    issues: list[dict[str, Any]],
    approval_role: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    if intent != "approve_existing_candidate":
        return intent, issues
    if not approval_role:
        return "generate_new_operator_candidate", [_default_missing_approval_issue()]
    approval_issues = candidate_approval_issues_for_role(issues, approval_role)
    return intent, approval_issues or [_default_candidate_approval_issue(approval_role)]


def normalize_operator_issue_draft(
    *,
    packet_sha256: str,
    draft: dict[str, Any],
    approval_role: str | None,
) -> tuple[str, list[dict[str, Any]]]:
    intent = _draft_intent(draft)
    issues = _normalized_draft_issues(draft)
    intent, issues = _resolve_approval_request(intent, issues, approval_role)
    issues = _cap_generated_issues(intent, issues) or [_fallback_human_needed_issue()]
    return intent, [_with_operator_issue_identity(packet_sha256, issue) for issue in issues]
