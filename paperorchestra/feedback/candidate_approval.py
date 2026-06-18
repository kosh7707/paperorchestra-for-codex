from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
