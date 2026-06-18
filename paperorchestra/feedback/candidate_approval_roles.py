from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.feedback.candidate_approval_blocking import _nested_candidate_approval_is_blocked
from paperorchestra.feedback.candidate_approval_payloads import _candidate_approval_payload, _without_sha256_prefix

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
