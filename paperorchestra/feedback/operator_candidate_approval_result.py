from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.feedback.operator_candidate_approval_readiness import CandidateApprovalReadiness
from paperorchestra.feedback.packet_artifacts import _sha256_prefixed


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
