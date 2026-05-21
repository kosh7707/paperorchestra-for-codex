from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .operator_feedback import (
    OPERATOR_FEEDBACK_INTENTS,
    OPERATOR_FEEDBACK_SCHEMA_VERSION,
    OPERATOR_SOURCE,
    derive_operator_issue_id,
)

_MAX_GENERATED_OPERATOR_ISSUES = 3
_OPERATOR_ISSUE_SEVERITY_RANK = {
    "blocker": 0,
    "critical": 0,
    "major": 1,
    "minor": 2,
}
_OPERATOR_ISSUE_ROLE_RANK = {
    "citation_support_review": 0,
    "figure_placement_review": 1,
    "quality_eval": 2,
    "citation_integrity_audit": 3,
    "qa_loop_execution": 4,
    "operator_feedback_execution": 5,
    "qa_loop_plan": 6,
}


def _without_sha256_prefix(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[1] if text.startswith("sha256:") else text


def _candidate_approval_payload(payload: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not isinstance(payload, dict):
        return None, None
    approval = payload.get("candidate_approval")
    progress = payload.get("candidate_progress")
    if not isinstance(approval, dict):
        candidate_result = payload.get("candidate_result")
        if isinstance(candidate_result, dict):
            approval = candidate_result.get("candidate_approval")
            progress = candidate_result.get("candidate_progress")
    return (approval if isinstance(approval, dict) else None, progress if isinstance(progress, dict) else None)


def _nested_candidate_approval_is_blocked(payload: dict[str, Any]) -> bool:
    """Return true when a nested approval is evidence of a failed approval attempt.

    Operator-feedback executions may carry a ``candidate_result`` from a prior
    approval attempt.  That nested candidate can still be hash-bound and have
    forward-progress metadata, but if the enclosing execution rolled it back for
    machine-solvable hard gates, re-offering the same approval just creates a
    human_needed loop.  Only top-level candidate approvals from the execution
    that generated a candidate are actionable.
    """

    if isinstance(payload.get("candidate_approval"), dict):
        return False
    candidate_result = payload.get("candidate_result")
    if not isinstance(candidate_result, dict) or not isinstance(candidate_result.get("candidate_approval"), dict):
        return False
    hard_reasons = {
        "tier2_claim_safety_new_failures",
        "active_tier2_metric_regression",
        "repeated_non_promotable_candidate",
        "citation_integrity_failed",
        "citation_integrity_audit_fail",
        "citation_source_match_fail",
        "claim_source_mismatch",
    }
    allowed_new_tier2 = {"citation_support_manual_check"}
    for attempt in payload.get("attempts") or []:
        if not isinstance(attempt, dict):
            continue
        reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
        new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
        if reasons & hard_reasons:
            return True
        if new_tier2 - allowed_new_tier2:
            return True
    return str(payload.get("promotion_status") or "") == "rolled_back"


def actionable_candidate_approval_role(packet: dict[str, Any]) -> str | None:
    """Return the artifact role for an unpromoted forward-progress candidate approval."""

    current_manuscript_sha = _without_sha256_prefix(packet.get("manuscript_sha256"))
    ready_roles: list[str] = []
    for artifact in packet.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        role = str(artifact.get("role") or "")
        if role not in {"qa_loop_execution", "operator_feedback_execution"}:
            continue
        try:
            payload = json.loads(Path(str(artifact.get("path") or "")).read_text(encoding="utf-8"))
        except Exception:
            continue
        approval, progress = _candidate_approval_payload(payload)
        if _nested_candidate_approval_is_blocked(payload):
            continue
        candidate_sha = _without_sha256_prefix((approval or {}).get("candidate_sha256"))
        if (
            approval
            and progress
            and approval.get("status") == "human_needed_candidate_ready"
            and progress.get("forward_progress") is True
            and candidate_sha
            and candidate_sha != current_manuscript_sha
        ):
            ready_roles.append(role)
    if "operator_feedback_execution" in ready_roles:
        return "operator_feedback_execution"
    if "qa_loop_execution" in ready_roles:
        return "qa_loop_execution"
    return None


def candidate_approval_issues_for_role(issues: list[dict[str, Any]], approval_role: str | None) -> list[dict[str, Any]]:
    """Return only the approval-target issues for an approve-existing request."""

    if approval_role not in {"qa_loop_execution", "operator_feedback_execution"}:
        return []
    return [issue for issue in issues if isinstance(issue, dict) and issue.get("source_artifact_role") == approval_role]


def normalize_operator_feedback_draft(packet: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    approval_role = actionable_candidate_approval_role(packet)
    intent = str(draft.get("intent") or draft.get("primary_intent") or "").strip()
    if not intent:
        raw_intents = draft.get("intents")
        if isinstance(raw_intents, list):
            intent = next((str(item).strip() for item in raw_intents if str(item or "").strip()), "")
    if not intent:
        # A ready candidate in the packet is evidence that approval is possible,
        # not authority to approve it.  Missing intent must continue through a
        # bounded operator-feedback candidate so conversational "proceed" style
        # responses cannot silently promote a manuscript.
        intent = "generate_new_operator_candidate"
    if intent not in OPERATOR_FEEDBACK_INTENTS:
        raise ValueError(f"unsupported operator feedback intent: {intent}")

    issues: list[dict[str, Any]] = []
    for raw in draft.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        issue = {
            key: str(raw.get(key) or "").strip()
            for key in [
                "source_artifact_role",
                "source_item_key",
                "target_section",
                "severity",
                "rationale",
                "suggested_action",
                "authority_class",
                "owner_category",
            ]
        }
        if not issue["rationale"] or not issue["suggested_action"]:
            continue
        issues.append(issue)

    if intent == "approve_existing_candidate":
        if approval_role:
            issues = candidate_approval_issues_for_role(issues, approval_role)
            if not issues:
                issues.insert(
                    0,
                    {
                        "source_artifact_role": approval_role,
                        "source_item_key": "candidate_approval",
                        "target_section": "Whole manuscript",
                        "severity": "major",
                        "rationale": "The packet exposes a forward-progress candidate approval artifact for supervised continuation.",
                        "suggested_action": "Approve the ready candidate so the next loop iteration can continue from the improved manuscript while preserving claim-safety gates.",
                        "authority_class": "author_feedback",
                        "owner_category": "author",
                    },
                )
        else:
            intent = "generate_new_operator_candidate"
            issues = [
                {
                    "source_artifact_role": "qa_loop_execution",
                    "source_item_key": "candidate_progress_without_candidate_approval",
                    "target_section": "Whole manuscript",
                    "severity": "major",
                    "rationale": "The operator requested approve_existing_candidate, but the packet has no actionable candidate_approval artifact; forward-progress diagnostics alone are not approval authority.",
                    "suggested_action": "Generate a new operator-feedback candidate from the current manuscript and the residual claim-safety issues instead of approving a non-ready candidate.",
                    "authority_class": "author_feedback",
                    "owner_category": "author",
                }
            ]

    if intent == "generate_new_operator_candidate" and len(issues) > _MAX_GENERATED_OPERATOR_ISSUES:
        indexed = list(enumerate(issues))
        indexed.sort(
            key=lambda pair: (
                _OPERATOR_ISSUE_SEVERITY_RANK.get(pair[1].get("severity", "").lower(), 3),
                _OPERATOR_ISSUE_ROLE_RANK.get(pair[1].get("source_artifact_role", ""), 9),
                pair[0],
            )
        )
        issues = [issue for _index, issue in indexed[:_MAX_GENERATED_OPERATOR_ISSUES]]

    if not issues:
        issues = [
            {
                "source_artifact_role": "qa_loop_plan",
                "source_item_key": "verdict:human_needed",
                "target_section": "Whole manuscript",
                "severity": "major",
                "rationale": "QA loop reached human_needed and needs bounded operator feedback.",
                "suggested_action": "Improve narrative coherence and claim-safety presentation while preserving paper-specific claims from the source packet only.",
                "authority_class": "author_feedback",
                "owner_category": "author",
            }
        ]

    for issue in issues:
        issue["id"] = derive_operator_issue_id(
            packet["packet_sha256"],
            source_artifact_role=issue["source_artifact_role"],
            source_item_key=issue["source_item_key"],
            target_section=issue["target_section"],
            rationale=issue["rationale"],
            suggested_action=issue["suggested_action"],
        )
        issue["source"] = OPERATOR_SOURCE
        issue["not_independent_human_review"] = True

    feedback = {
        "schema_version": OPERATOR_FEEDBACK_SCHEMA_VERSION,
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "intent": intent,
        "packet_sha256": packet["packet_sha256"],
        "manuscript_sha256": packet["manuscript_sha256"],
        "issues": issues,
    }
    if isinstance(draft.get("human_needed_answer"), dict):
        feedback["human_needed_answer"] = dict(draft["human_needed_answer"])
    return feedback
