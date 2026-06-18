from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HARD_APPROVAL_ROLLBACK_REASONS = {
    "tier2_claim_safety_new_failures",
    "active_tier2_metric_regression",
    "repeated_non_promotable_candidate",
    "citation_integrity_failed",
    "citation_integrity_audit_fail",
    "citation_source_match_fail",
    "claim_source_mismatch",
}
_ALLOWED_NEW_TIER2_FAILURES = {"citation_support_manual_check"}


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
    if isinstance(payload.get("candidate_approval"), dict):
        return False
    candidate_result = payload.get("candidate_result")
    if not isinstance(candidate_result, dict) or not isinstance(candidate_result.get("candidate_approval"), dict):
        return False
    for attempt in payload.get("attempts") or []:
        if not isinstance(attempt, dict):
            continue
        reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
        new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
        if reasons & _HARD_APPROVAL_ROLLBACK_REASONS:
            return True
        if new_tier2 - _ALLOWED_NEW_TIER2_FAILURES:
            return True
    return str(payload.get("promotion_status") or "") == "rolled_back"


_APPROVAL_ARTIFACT_ROLES = {"qa_loop_execution", "operator_feedback_execution"}


def actionable_candidate_approval_role(packet: dict[str, Any]) -> str | None:
    """Return the artifact role for an unpromoted forward-progress candidate approval."""

    current_manuscript_sha = _without_sha256_prefix(packet.get("manuscript_sha256"))
    ready_roles: list[str] = []
    for artifact in packet.get("artifacts") or []:
        role, payload = _approval_artifact_payload(artifact)
        if role is None or payload is None or _nested_candidate_approval_is_blocked(payload):
            continue
        approval, progress = _candidate_approval_payload(payload)
        candidate_sha = _without_sha256_prefix((approval or {}).get("candidate_sha256"))
        if _approval_is_actionable(approval, progress, candidate_sha, current_manuscript_sha):
            ready_roles.append(role)
    if "operator_feedback_execution" in ready_roles:
        return "operator_feedback_execution"
    if "qa_loop_execution" in ready_roles:
        return "qa_loop_execution"
    return None


def _approval_artifact_payload(artifact: Any) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(artifact, dict):
        return None, None
    role = str(artifact.get("role") or "")
    if role not in _APPROVAL_ARTIFACT_ROLES:
        return None, None
    try:
        payload = json.loads(Path(str(artifact.get("path") or "")).read_text(encoding="utf-8"))
    except Exception:
        return role, None
    return role, payload if isinstance(payload, dict) else None


def _approval_is_actionable(
    approval: dict[str, Any] | None,
    progress: dict[str, Any] | None,
    candidate_sha: str,
    current_manuscript_sha: str,
) -> bool:
    return (
        bool(approval)
        and bool(progress)
        and approval.get("status") == "human_needed_candidate_ready"
        and progress.get("forward_progress") is True
        and bool(candidate_sha)
        and candidate_sha != current_manuscript_sha
    )
