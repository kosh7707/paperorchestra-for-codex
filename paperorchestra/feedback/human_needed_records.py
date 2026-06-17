from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_answer_metadata import (
    HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
    HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION,
)
from paperorchestra.feedback.packets import _artifact_by_role


def _action_id(action: dict[str, Any] | None) -> str:
    if not isinstance(action, dict):
        return ""
    return str(action.get("id") or action.get("action_id") or "").strip()


def _artifact_source(packet: dict[str, Any], role: str | None) -> dict[str, str] | None:
    if not role:
        return None
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    return {
        "role": str(record.get("role") or role),
        "sha256": str(record.get("sha256") or ""),
    }


def _metadata_without_targets(
    *,
    packet: dict[str, Any],
    packet_file_sha256: str,
    answer_sha256: str,
    private_answer_artifact_sha256: str | None,
    decision_kind: str,
    handoff_type: str,
    action: dict[str, Any] | None,
    candidate_role: str | None,
) -> dict[str, Any]:
    selected = _artifact_source(packet, candidate_role or "qa_loop_plan")
    return {
        "schema_version": HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
        "session_id": packet.get("session_id"),
        "packet_sha256": packet.get("packet_sha256"),
        "packet_file_sha256": packet_file_sha256,
        "manuscript_sha256": packet.get("manuscript_sha256"),
        "answer_sha256": answer_sha256,
        "private_answer_artifact_sha256": private_answer_artifact_sha256,
        "decision_kind": decision_kind,
        "handoff_type": handoff_type,
        "target_action_id": _action_id(action) or None,
        "selected_handoff_source": selected,
        "answer": "redacted",
    }


def public_answer_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    payload = dict(metadata)
    payload["schema_version"] = HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION
    return payload


def public_result_payload(public_payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(public_payload)
    result["answer"] = "redacted"
    result["execution"] = "human_needed_answer_recorded"
    return result
