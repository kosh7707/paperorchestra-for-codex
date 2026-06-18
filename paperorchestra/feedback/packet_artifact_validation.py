from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session
from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.packet_execution_openers import _execution_payload_opens_operator_review
from paperorchestra.feedback.packet_plan_validation import _validate_current_operator_plan

_BOUND_ARTIFACT_ROLES = {
    "quality_eval",
    "qa_loop_plan",
    "qa_loop_execution",
    "operator_feedback_execution",
    "citation_support_review",
    "citation_integrity_audit",
    "citation_integrity_critic",
    "figure_placement_review",
    "section_review",
}
_REQUIRED_BOUND_SHA_ROLES = {"qa_loop_plan", "figure_placement_review"}
_HUMAN_NEEDED_EXECUTION_ROLES = {"qa_loop_execution", "operator_feedback_execution"}


def _validate_operator_packet_artifact_bindings(
    *,
    cwd: str | Path | None,
    packet: dict[str, Any],
    current_manuscript_sha256: str,
) -> None:
    state = load_session(cwd)
    if packet.get("session_id") != state.session_id:
        raise ContractError("operator review packet session_id does not match current session")
    current_sha = _packet_artifacts._file_sha256(state.artifacts.paper_full_tex)
    if current_sha != current_manuscript_sha256:
        raise ContractError("operator review packet manuscript hash is stale for the current manuscript")

    artifacts = packet.get("artifacts") if isinstance(packet.get("artifacts"), list) else []
    records_by_role = {str(record.get("role")): record for record in artifacts if isinstance(record, dict)}
    has_operator_review_context = _has_operator_review_context(records_by_role, current_manuscript_sha256)
    _validate_current_operator_plan(
        cwd=cwd,
        session_id=state.session_id,
        current_manuscript_sha256=current_manuscript_sha256,
        allow_operator_review_context=has_operator_review_context,
    )
    plan_payload = _validated_plan_payload(records_by_role, has_operator_review_context=has_operator_review_context)
    for role in _BOUND_ARTIFACT_ROLES:
        _validate_bound_artifact(
            records_by_role.get(role),
            role=role,
            current_manuscript_sha256=current_manuscript_sha256,
            plan_payload=plan_payload,
            has_operator_review_context=has_operator_review_context,
        )


def _has_operator_review_context(records_by_role: dict[str, dict[str, Any]], current_manuscript_sha256: str) -> bool:
    qa_execution_record = records_by_role.get("qa_loop_execution")
    if not qa_execution_record:
        return False
    qa_execution_payload = _packet_bindings._artifact_payload(qa_execution_record)
    if not isinstance(qa_execution_payload, dict):
        return False
    return _execution_payload_opens_operator_review(
        Path(str(qa_execution_record.get("original_path") or qa_execution_record.get("path"))),
        qa_execution_payload,
        current_manuscript_sha256=current_manuscript_sha256,
    )


def _validated_plan_payload(
    records_by_role: dict[str, dict[str, Any]],
    *,
    has_operator_review_context: bool,
) -> dict[str, Any]:
    plan_record = records_by_role.get("qa_loop_plan")
    if not plan_record:
        raise ContractError("operator review packet requires a current qa_loop_plan artifact")
    plan_payload = _packet_bindings._artifact_payload(plan_record)
    if not isinstance(plan_payload, dict):
        raise ContractError("operator review packet requires readable qa_loop_plan artifact")
    if has_operator_review_context:
        if plan_payload.get("verdict") not in {"continue", "human_needed"}:
            raise ContractError("operator review packet operator stop requires qa_loop_plan verdict=continue or human_needed")
    elif plan_payload.get("verdict") != "human_needed":
        raise ContractError("operator review packet requires qa_loop_plan verdict=human_needed")
    return plan_payload


def _validate_bound_artifact(
    record: dict[str, Any] | None,
    *,
    role: str,
    current_manuscript_sha256: str,
    plan_payload: dict[str, Any],
    has_operator_review_context: bool,
) -> None:
    if not record:
        return
    payload = _packet_bindings._artifact_payload(record)
    if payload is None:
        raise ContractError(f"operator review packet artifact is unreadable: {role}")
    bound_sha = _packet_bindings._artifact_bound_manuscript_sha(role, payload)
    if bound_sha is None:
        if role in _REQUIRED_BOUND_SHA_ROLES:
            raise ContractError(f"operator review packet artifact lacks manuscript hash binding: {role}")
        return
    if _allows_previous_human_needed_execution_hash(
        role,
        bound_sha=bound_sha,
        current_manuscript_sha256=current_manuscript_sha256,
        plan_payload=plan_payload,
        has_operator_review_context=has_operator_review_context,
    ):
        return
    if bound_sha != current_manuscript_sha256:
        raise ContractError(f"operator review packet artifact is stale for current manuscript: {role}")


def _allows_previous_human_needed_execution_hash(
    role: str,
    *,
    bound_sha: str,
    current_manuscript_sha256: str,
    plan_payload: dict[str, Any],
    has_operator_review_context: bool,
) -> bool:
    return (
        role in _HUMAN_NEEDED_EXECUTION_ROLES
        and not has_operator_review_context
        and plan_payload.get("verdict") == "human_needed"
        and bound_sha != current_manuscript_sha256
    )
