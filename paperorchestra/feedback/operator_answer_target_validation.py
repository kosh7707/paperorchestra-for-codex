from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.feedback.operator_answer_constants import HUMAN_NEEDED_SELECTED_SOURCE_ALLOWED_KEYS
from paperorchestra.feedback.packet_records import _artifact_by_role


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
