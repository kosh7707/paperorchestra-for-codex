from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.feedback import packet_artifacts as _packet_artifacts
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.packet_discovery import (
    _current_bound_execution_path,
    _execution_payload_opens_candidate_review,
    _execution_payload_opens_operator_review,
    _first_current_bound_existing,
    _first_existing,
    _latest_human_needed_execution,
    _latest_human_needed_operator_feedback_execution,
    _operator_review_human_needed_artifacts,
)


def _artifact_by_role(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    for artifact in packet.get("artifacts") or []:
        if isinstance(artifact, dict) and artifact.get("role") == role:
            return artifact
    return None


def _packet_has_human_needed_context(packet: dict[str, Any]) -> bool:
    for role in ("qa_loop_plan", "qa_loop_execution", "operator_feedback_execution"):
        record = _artifact_by_role(packet, role)
        if not record:
            continue
        try:
            payload = read_json(record["path"])
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("verdict") == "human_needed":
            return True
    return False


def _validate_current_operator_plan(
    *,
    cwd: str | Path | None,
    session_id: str,
    current_manuscript_sha256: str,
    allow_operator_review_context: bool = False,
) -> None:
    plan_path = artifact_path(cwd, "qa-loop.plan.json")
    try:
        plan = read_json(plan_path)
    except Exception as exc:
        raise ContractError("operator feedback requires readable current qa-loop.plan.json") from exc
    if not isinstance(plan, dict):
        raise ContractError("operator feedback requires readable current qa-loop.plan.json")
    plan_verdict = plan.get("verdict")
    if allow_operator_review_context:
        if plan_verdict not in {"continue", "human_needed"}:
            raise ContractError(
                "operator feedback operator review stop requires current qa-loop.plan.json verdict=continue or human_needed"
            )
    elif plan_verdict != "human_needed":
        raise ContractError("operator feedback requires current qa-loop.plan.json verdict=human_needed")
    if plan.get("session_id") != session_id:
        raise ContractError("operator feedback current qa-loop.plan.json session_id mismatch")
    bound_sha = _packet_bindings._artifact_bound_manuscript_sha("qa_loop_plan", plan)
    if bound_sha is None:
        raise ContractError("operator feedback current qa-loop.plan.json lacks manuscript hash binding")
    if bound_sha != current_manuscript_sha256:
        raise ContractError("operator feedback current qa-loop.plan.json is stale for current manuscript")


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
    qa_execution_payload = None
    qa_execution_record = records_by_role.get("qa_loop_execution")
    if qa_execution_record:
        qa_execution_payload = _packet_bindings._artifact_payload(qa_execution_record)
    has_operator_review_context = (
        isinstance(qa_execution_payload, dict)
        and _execution_payload_opens_operator_review(
            Path(str(qa_execution_record.get("original_path") or qa_execution_record.get("path"))),
            qa_execution_payload,
            current_manuscript_sha256=current_manuscript_sha256,
        )
    )
    _validate_current_operator_plan(
        cwd=cwd,
        session_id=state.session_id,
        current_manuscript_sha256=current_manuscript_sha256,
        allow_operator_review_context=has_operator_review_context,
    )
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

    for role in {
        "quality_eval",
        "qa_loop_plan",
        "qa_loop_execution",
        "operator_feedback_execution",
        "citation_support_review",
        "citation_integrity_audit",
        "citation_integrity_critic",
        "figure_placement_review",
        "section_review",
    }:
        record = records_by_role.get(role)
        if not record:
            continue
        payload = _packet_bindings._artifact_payload(record)
        if payload is None:
            raise ContractError(f"operator review packet artifact is unreadable: {role}")
        bound_sha = _packet_bindings._artifact_bound_manuscript_sha(role, payload)
        if bound_sha is None:
            if role in {"qa_loop_plan", "figure_placement_review"}:
                raise ContractError(f"operator review packet artifact lacks manuscript hash binding: {role}")
            continue
        if (
            role in {"qa_loop_execution", "operator_feedback_execution"}
            and not has_operator_review_context
            and isinstance(plan_payload, dict)
            and plan_payload.get("verdict") == "human_needed"
            and bound_sha != current_manuscript_sha256
        ):
            continue
        if bound_sha != current_manuscript_sha256:
            raise ContractError(f"operator review packet artifact is stale for current manuscript: {role}")
