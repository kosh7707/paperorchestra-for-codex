from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.packet_execution_discovery import _first_existing


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
    source_path_text = str(approval.get("source_execution_path") or "").strip()
    if not source_path_text:
        return False
    try:
        if Path(source_path_text).resolve() != execution_path.resolve():
            return False
    except Exception:
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
    reason = str(payload.get("reason") or "")
    if reason in {"no_supported_executable_handlers"}:
        return True
    return False


def _current_bound_execution_path(path: Path | None, *, role: str, current_manuscript_sha256: str | None) -> Path | None:
    if path is None or not current_manuscript_sha256:
        return path
    try:
        payload = read_json(path)
    except Exception:
        return path
    if not isinstance(payload, dict):
        return path
    bound_sha = _packet_bindings._artifact_bound_manuscript_sha(role, payload)
    if role == "figure_placement_review" and bound_sha is None:
        return None
    if bound_sha is not None and bound_sha != current_manuscript_sha256:
        return None
    return path


def _first_current_bound_existing(
    role: str,
    current_manuscript_sha256: str | None,
    *paths: str | Path | None,
) -> Path | None:
    for path in paths:
        candidate = _first_existing(path)
        if candidate is None:
            continue
        current = _current_bound_execution_path(
            candidate,
            role=role,
            current_manuscript_sha256=current_manuscript_sha256,
        )
        if current is not None:
            return current
    return None
