from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings


def _execution_payload_opens_candidate_review(
    execution_path: Path,
    payload: dict[str, Any],
    *,
    current_manuscript_sha256: str,
) -> bool:
    if payload.get("verdict") != "human_needed":
        return False
    approval = payload.get("candidate_approval")
    if not isinstance(approval, dict) or approval.get("status") != "human_needed_candidate_ready":
        return False
    if _packet_bindings._normalized_sha(approval.get("base_manuscript_sha256")) != current_manuscript_sha256:
        return False
    if not approval.get("created_at"):
        return False
    if not _approval_source_matches_execution(execution_path, approval):
        return False
    if str(approval.get("source_execution_sha256") or "") != _packet_bindings._execution_payload_sha256(payload):
        return False
    candidate_path = approval.get("candidate_path")
    candidate_sha = _packet_bindings._normalized_sha(approval.get("candidate_sha256"))
    if not candidate_path or not candidate_sha:
        return False
    if _packet_bindings._normalized_sha(_packet_artifacts._file_sha256(candidate_path)) != candidate_sha:
        return False
    progress = payload.get("candidate_progress")
    if isinstance(progress, dict) and progress.get("forward_progress") is not True:
        return False
    return True


def _approval_source_matches_execution(execution_path: Path, approval: dict[str, Any]) -> bool:
    source_path_text = str(approval.get("source_execution_path") or "").strip()
    if not source_path_text:
        return False
    try:
        return Path(source_path_text).resolve() == execution_path.resolve()
    except Exception:
        return False


def _execution_payload_opens_operator_review(
    execution_path: Path,
    payload: dict[str, Any],
    *,
    current_manuscript_sha256: str,
) -> bool:
    if _execution_payload_opens_candidate_review(
        execution_path,
        payload,
        current_manuscript_sha256=current_manuscript_sha256,
    ):
        return True
    if payload.get("verdict") != "human_needed":
        return False
    bound_sha = _packet_bindings._artifact_bound_manuscript_sha("qa_loop_execution", payload)
    if bound_sha != current_manuscript_sha256:
        return False
    if payload.get("no_progress_override") is True:
        return True
    handoff = payload.get("candidate_handoff")
    if isinstance(handoff, dict) and str(handoff.get("status") or "").startswith("human_needed_candidate_rejected"):
        return True
    return str(payload.get("reason") or "") in {"no_supported_executable_handlers"}
