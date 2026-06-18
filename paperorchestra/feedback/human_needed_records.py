from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_answer_metadata import (
    HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
    HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION,
)
from paperorchestra.feedback.packet_records import _artifact_by_role


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


def private_answer_payload(
    *,
    schema_version: str,
    recorded_at: str,
    packet: dict[str, Any],
    packet_file_sha256: str,
    answer_sha256: str,
    answer: str,
    decision_kind: str,
    handoff_type: str,
    action: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "recorded_at": recorded_at,
        "session_id": packet.get("session_id"),
        "packet_sha256": packet.get("packet_sha256"),
        "packet_file_sha256": packet_file_sha256,
        "manuscript_sha256": packet.get("manuscript_sha256"),
        "answer_sha256": answer_sha256,
        "answer": answer,
        "decision_kind": decision_kind,
        "handoff_type": handoff_type,
        "target_action_id": _action_id(action) or None,
    }


def _draft_issue_for_action(
    *,
    action: dict[str, Any] | None,
    handoff_type: str,
    decision_kind: str,
    candidate_role: str | None,
) -> dict[str, Any]:
    if candidate_role and decision_kind == "approve_existing_candidate":
        return {
            "source_artifact_role": candidate_role,
            "source_item_key": "candidate_approval",
            "target_section": "Whole manuscript",
            "severity": "major",
            "rationale": "The operator explicitly approved a hash-bound forward-progress candidate exposed by the human_needed packet.",
            "suggested_action": (
                "Import this as approve_existing_candidate author feedback. "
                "apply_operator_feedback must re-read the packet-bound candidate_approval, verify candidate/base/source hashes "
                "and forward-progress evidence, then promote only after the operator-feedback hard gate passes."
            ),
            "authority_class": "author_feedback",
            "owner_category": "author",
        }
    source_key = str((action or {}).get("code") or _action_id(action) or f"human_needed:{handoff_type}")
    target = str((action or {}).get("target") or "Whole manuscript")
    reason = str((action or {}).get("reason") or "The QA loop reached human_needed and requires bounded operator judgment.")
    if decision_kind == "reject_candidate_with_reason":
        suggested = "Reject the currently exposed candidate or unsafe direction; keep the canonical manuscript unchanged and request a safer repair plan."
    else:
        suggested = "Generate a bounded operator-feedback candidate that addresses this human_needed handoff using only packet-grounded manuscript evidence."
    return {
        "source_artifact_role": "qa_loop_plan",
        "source_item_key": source_key,
        "target_section": target,
        "severity": "major",
        "rationale": reason,
        "suggested_action": suggested,
        "authority_class": "author_feedback",
        "owner_category": "author",
    }


def feedback_draft(
    *,
    action: dict[str, Any] | None,
    handoff_type: str,
    decision_kind: str,
    candidate_role: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "intent": decision_kind,
        "issues": [
            _draft_issue_for_action(
                action=action,
                handoff_type=handoff_type,
                decision_kind=decision_kind,
                candidate_role=candidate_role,
            )
        ],
        "human_needed_answer": metadata,
    }
