from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_candidate_packets import _packet_artifact_payload
from paperorchestra.feedback.packet_artifacts import _file_sha256, _sha256_digest, _sha256_prefixed
from paperorchestra.feedback.packet_bindings import _execution_payload_sha256
from paperorchestra.feedback.packets import _artifact_by_role


def _candidate_approval_source_role(imported: dict[str, Any]) -> str | None:
    roles = {
        str(issue.get("source_artifact_role") or "")
        for issue in imported.get("issues") or []
        if isinstance(issue, dict) and str(issue.get("source_artifact_role") or "") in {"qa_loop_execution", "operator_feedback_execution"}
    }
    if len(roles) > 1:
        raise ContractError("approve_existing_candidate feedback must target exactly one candidate approval source artifact")
    return next(iter(roles), None)


def _candidate_source_execution_from_packet(packet: dict[str, Any], preferred_role: str | None = None) -> tuple[dict[str, Any], str]:
    roles = (preferred_role,) if preferred_role else ("qa_loop_execution", "operator_feedback_execution")
    for role in roles:
        if role not in {"qa_loop_execution", "operator_feedback_execution"}:
            raise ContractError("approve_existing_candidate targets an unsupported candidate approval source artifact")
        payload = _packet_artifact_payload(packet, role)
        if isinstance(payload, dict) and isinstance(payload.get("candidate_approval"), dict):
            return payload, role
        if role == "operator_feedback_execution" and isinstance(payload, dict):
            candidate_result = payload.get("candidate_result")
            if isinstance(candidate_result, dict):
                source_execution = candidate_result.get("source_execution")
                if isinstance(source_execution, dict) and isinstance(source_execution.get("candidate_approval"), dict):
                    return source_execution, role
    raise ContractError("approve_existing_candidate requires candidate approval execution evidence")


def _ready_candidate_from_packet(packet: dict[str, Any], current_sha: str | None, *, source_artifact_role: str | None = None) -> dict[str, Any]:
    execution, execution_role = _candidate_source_execution_from_packet(packet, source_artifact_role)
    approval = execution.get("candidate_approval") if isinstance(execution, dict) else None
    progress = execution.get("candidate_progress") if isinstance(execution, dict) else None
    candidate_state = execution.get("candidate_state") if isinstance(execution, dict) else None
    restored_current_state = execution.get("restored_current_state") if isinstance(execution, dict) else None
    if not isinstance(approval, dict) or approval.get("status") != "human_needed_candidate_ready":
        raise ContractError("approve_existing_candidate requires human_needed_candidate_ready evidence")
    missing_approval = [
        key
        for key in (
            "candidate_path",
            "candidate_sha256",
            "base_manuscript_sha256",
            "source_execution_path",
            "source_execution_sha256",
            "created_at",
        )
        if not str(approval.get(key) or "").strip()
    ]
    if missing_approval:
        raise ContractError("approve_existing_candidate missing candidate_approval." + ", candidate_approval.".join(missing_approval))
    if not isinstance(progress, dict) or progress.get("forward_progress") is not True:
        raise ContractError("approve_existing_candidate requires candidate_progress.forward_progress=true")
    for key in ("before_failing_codes", "after_failing_codes"):
        if key not in progress:
            raise ContractError(f"approve_existing_candidate missing candidate_progress.{key}")
    before_progress_codes = {str(code) for code in progress.get("before_failing_codes") or []}
    after_progress_codes = {str(code) for code in progress.get("after_failing_codes") or []}
    citation_issue_delta = progress.get("citation_issue_delta")
    citation_issue_count_improved = isinstance(citation_issue_delta, int) and citation_issue_delta < 0
    if before_progress_codes and not (before_progress_codes - after_progress_codes) and not citation_issue_count_improved:
        raise ContractError("approve_existing_candidate requires resolved active blockers or reduced citation issue count")
    candidate_verification = candidate_state.get("verification") if isinstance(candidate_state, dict) else None
    restored_verification = restored_current_state.get("verification") if isinstance(restored_current_state, dict) else None
    if not isinstance(candidate_verification, dict) and not isinstance(restored_verification, dict):
        raise ContractError("approve_existing_candidate requires candidate_state.verification or restored_current_state.verification")
    candidate_path = Path(str(approval.get("candidate_path") or "")).resolve()
    if not candidate_path.exists() or not candidate_path.is_file():
        raise ContractError("approved QA candidate file is missing")
    expected_candidate = _sha256_digest(str(approval.get("candidate_sha256") or ""))
    actual_candidate = _file_sha256(candidate_path)
    if not expected_candidate or expected_candidate != actual_candidate:
        raise ContractError("approved QA candidate hash mismatch")
    expected_base = _sha256_digest(str(approval.get("base_manuscript_sha256") or ""))
    if expected_base and current_sha and expected_base != current_sha:
        raise ContractError("approved QA candidate base manuscript hash mismatch")
    expected_source_sha = str(approval.get("source_execution_sha256") or "")
    actual_source_sha = _execution_payload_sha256(execution)
    source_path = approval.get("source_execution_path")
    source_record = _artifact_by_role(packet, execution_role)
    if source_path and source_record:
        approved_source = Path(str(source_path)).resolve()
        packet_sources = {Path(str(source_record["path"])).resolve()}
        if source_record.get("original_path"):
            packet_sources.add(Path(str(source_record["original_path"])).resolve())
        embedded_operator_source = execution_role == "operator_feedback_execution" and expected_source_sha == actual_source_sha
        if approved_source not in packet_sources and not embedded_operator_source:
            raise ContractError("approved QA candidate source execution path mismatch")
    if expected_source_sha != actual_source_sha:
        raise ContractError("approved QA candidate source execution hash mismatch")
    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": _sha256_prefixed(actual_candidate),
        "candidate_approval": approval,
        "candidate_progress": progress,
        "candidate_state": candidate_state,
        "source_execution": execution,
        "executor_environment": "preexisting_candidate",
        "executor_path": "operator_feedback._ready_candidate_from_packet",
        "executor_trace_artifact": str(source_path),
        "executor_failure_category": "none",
        "executor_source_role": execution_role,
    }
