from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.feedback.operator_answer_constants import (
    HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS,
    HUMAN_NEEDED_HANDOFF_TYPES,
    HUMAN_NEEDED_METADATA_ALLOWED_KEYS,
    HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
    HUMAN_NEEDED_SELECTED_SOURCE_ALLOWED_KEYS,
    OPERATOR_FEEDBACK_INTENTS,
)
from paperorchestra.feedback.operator_answer_redaction import _contains_forbidden_human_needed_metadata
from paperorchestra.feedback.packet_artifacts import _file_sha256
from paperorchestra.feedback.packets import _artifact_by_role


def _validate_human_needed_answer_metadata(
    metadata: Any,
    packet: dict[str, Any],
    imported_issue_ids: set[str],
    *,
    packet_path: str | Path,
    intent: str,
    imported_issue_roles: set[str],
) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise ContractError("human_needed_answer metadata must be a JSON object")
    _validate_metadata_shape(metadata)
    _validate_packet_binding(metadata, packet, packet_path=packet_path)
    decision_kind = _validate_decision_kind(metadata, intent)
    handoff_type = _validate_handoff_type(metadata)
    _validate_digest_fields(metadata)
    _validate_selected_handoff_source(
        metadata,
        packet,
        handoff_type=handoff_type,
        imported_issue_roles=imported_issue_roles,
    )
    _validate_target_action_id(metadata, packet)
    _validate_target_issue_ids(metadata, imported_issue_ids)
    normalized = dict(metadata)
    normalized["schema_version"] = HUMAN_NEEDED_METADATA_SCHEMA_VERSION
    normalized["answer"] = "redacted"
    return normalized


def _validate_metadata_shape(metadata: dict[str, Any]) -> None:
    unexpected_keys = sorted(set(metadata) - HUMAN_NEEDED_METADATA_ALLOWED_KEYS)
    if unexpected_keys:
        raise ContractError("human_needed_answer metadata contains unsupported fields: " + ", ".join(unexpected_keys))
    if metadata.get("schema_version") not in HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS:
        raise ContractError("human_needed_answer metadata has an unsupported schema_version")
    if _contains_forbidden_human_needed_metadata(metadata):
        raise ContractError("human_needed_answer metadata must not contain raw/private answer data")


def _validate_packet_binding(metadata: dict[str, Any], packet: dict[str, Any], *, packet_path: str | Path) -> None:
    if metadata.get("session_id") != packet.get("session_id"):
        raise ContractError("human_needed_answer session_id does not match packet")
    if metadata.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("human_needed_answer packet_sha256 does not match packet")
    if metadata.get("manuscript_sha256") != packet.get("manuscript_sha256"):
        raise ContractError("human_needed_answer manuscript_sha256 does not match packet")
    packet_file_sha = str(metadata.get("packet_file_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", packet_file_sha):
        raise ContractError("human_needed_answer packet_file_sha256 must be a sha256 digest")
    if _file_sha256(packet_path) != packet_file_sha:
        raise ContractError("human_needed_answer packet_file_sha256 does not match packet file")


def _validate_decision_kind(metadata: dict[str, Any], intent: str) -> str:
    decision_kind = str(metadata.get("decision_kind") or "")
    if decision_kind not in OPERATOR_FEEDBACK_INTENTS:
        raise ContractError("human_needed_answer decision_kind is unsupported")
    if decision_kind != intent:
        raise ContractError("human_needed_answer decision_kind does not match operator feedback intent")
    return decision_kind


def _validate_handoff_type(metadata: dict[str, Any]) -> str:
    handoff_type = str(metadata.get("handoff_type") or "")
    if handoff_type not in HUMAN_NEEDED_HANDOFF_TYPES:
        raise ContractError("human_needed_answer handoff_type is unsupported")
    return handoff_type


def _validate_digest_fields(metadata: dict[str, Any]) -> None:
    for key in ("answer_sha256",):
        value = str(metadata.get(key) or "")
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", value):
            raise ContractError(f"human_needed_answer {key} must be a sha256 digest")
    private_sha = metadata.get("private_answer_artifact_sha256")
    if private_sha is not None and not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", str(private_sha)):
        raise ContractError("human_needed_answer private_answer_artifact_sha256 must be a sha256 digest")


def _validate_selected_handoff_source(
    metadata: dict[str, Any],
    packet: dict[str, Any],
    *,
    handoff_type: str,
    imported_issue_roles: set[str],
) -> None:
    selected = metadata.get("selected_handoff_source")
    if selected is None:
        return
    if not isinstance(selected, dict):
        raise ContractError("human_needed_answer selected_handoff_source must be an object")
    unexpected_selected_keys = sorted(set(selected) - HUMAN_NEEDED_SELECTED_SOURCE_ALLOWED_KEYS)
    if unexpected_selected_keys:
        raise ContractError(
            "human_needed_answer selected_handoff_source contains unsupported fields: "
            + ", ".join(unexpected_selected_keys)
        )
    role = str(selected.get("role") or "")
    sha = str(selected.get("sha256") or "")
    record = _artifact_by_role(packet, role)
    if not record or str(record.get("sha256") or "") != sha:
        raise ContractError("human_needed_answer selected_handoff_source is not bound to the packet")
    if imported_issue_roles and imported_issue_roles != {role}:
        raise ContractError("human_needed_answer selected_handoff_source does not match imported issue sources")
    if handoff_type == "candidate_approval" and role not in {"qa_loop_execution", "operator_feedback_execution"}:
        raise ContractError("human_needed_answer candidate_approval must select a candidate execution source")
    if handoff_type != "candidate_approval" and role in {"qa_loop_execution", "operator_feedback_execution"}:
        raise ContractError("human_needed_answer non-candidate handoff selected a candidate execution source")


def _validate_target_action_id(metadata: dict[str, Any], packet: dict[str, Any]) -> None:
    target_action_id = str(metadata.get("target_action_id") or "")
    if not target_action_id:
        return
    plan_record = _artifact_by_role(packet, "qa_loop_plan")
    try:
        plan = read_json(plan_record["path"]) if plan_record else {}
    except Exception:
        plan = {}
    actions = plan.get("repair_actions") if isinstance(plan, dict) else []
    known_action_ids = {
        str(action.get("id") or action.get("action_id") or "")
        for action in actions or []
        if isinstance(action, dict)
    }
    if target_action_id not in known_action_ids:
        raise ContractError("human_needed_answer target_action_id is not present in the packet qa_loop_plan")


def _validate_target_issue_ids(metadata: dict[str, Any], imported_issue_ids: set[str]) -> None:
    target_ids = metadata.get("target_issue_ids") or []
    if not isinstance(target_ids, list):
        raise ContractError("human_needed_answer target_issue_ids must be a list")
    missing = [str(issue_id) for issue_id in target_ids if str(issue_id) not in imported_issue_ids]
    if missing:
        raise ContractError("human_needed_answer target_issue_ids do not match imported issues: " + ", ".join(missing))
