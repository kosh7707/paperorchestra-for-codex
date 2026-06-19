from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.feedback.operator_candidate_approval_hashes import (
    _verified_candidate_file,
    _verify_base_hash,
    _verify_source_binding,
)
from paperorchestra.feedback.operator_candidate_approval_readiness import CandidateApprovalReadiness
from paperorchestra.feedback.packet_artifacts import _sha256_prefixed
from paperorchestra.feedback.operator_candidate_approval_sources import _candidate_source_execution_from_packet


def _ready_candidate_result(readiness: CandidateApprovalReadiness, candidate_path: Path, candidate_sha: str) -> dict[str, Any]:
    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": _sha256_prefixed(candidate_sha),
        "candidate_approval": readiness.approval,
        "candidate_progress": readiness.progress,
        "candidate_state": readiness.candidate_state,
        "source_execution": readiness.execution,
        "executor_environment": "preexisting_candidate",
        "executor_path": "operator_feedback._ready_candidate_from_packet",
        "executor_trace_artifact": str(readiness.approval.get("source_execution_path")),
        "executor_failure_category": "none",
        "executor_source_role": readiness.execution_role,
    }


def _ready_candidate_from_packet(packet: dict[str, Any], current_sha: str | None, *, source_artifact_role: str | None = None) -> dict[str, Any]:
    execution, execution_role = _candidate_source_execution_from_packet(packet, source_artifact_role)
    readiness = CandidateApprovalReadiness.from_execution(execution, execution_role)
    readiness.require_blocker_progress()
    readiness.require_verification_evidence()
    candidate_path, candidate_sha = _verified_candidate_file(readiness.approval)
    _verify_base_hash(readiness.approval, current_sha)
    _verify_source_binding(packet=packet, execution=execution, execution_role=execution_role, approval=readiness.approval)
    return _ready_candidate_result(readiness, candidate_path, candidate_sha)
