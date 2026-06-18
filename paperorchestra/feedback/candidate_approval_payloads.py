from __future__ import annotations

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
