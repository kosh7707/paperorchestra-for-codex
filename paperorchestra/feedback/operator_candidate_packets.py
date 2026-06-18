from __future__ import annotations

from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.feedback.operator_contract import _read_packet
from paperorchestra.feedback.packet_bindings import _artifact_bound_manuscript_sha, _normalized_sha
from paperorchestra.feedback.packet_records import _artifact_by_role


def _load_packet_from_imported(imported: dict[str, Any]) -> dict[str, Any]:
    return _read_packet(imported.get("packet_path"))


def _packet_artifact_payload(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    payload = read_json(record["path"])
    return payload if isinstance(payload, dict) else None


def _operator_execution_matches_packet_manuscript(
    payload: dict[str, Any],
    packet_manuscript_sha256: str | None,
) -> bool:
    bound_sha = _artifact_bound_manuscript_sha("operator_feedback_execution", payload)
    packet_sha = _normalized_sha(packet_manuscript_sha256)
    return bool(bound_sha and packet_sha and bound_sha == packet_sha)


def _packet_prior_operator_attempts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract failed-attempt memory from packet-carried operator executions."""

    payload = _packet_artifact_payload(packet, "operator_feedback_execution")
    packet_sha = str(packet.get("manuscript_sha256") or "")
    payloads: list[dict[str, Any]] = []
    if isinstance(payload, dict) and _operator_execution_matches_packet_manuscript(payload, packet_sha):
        payloads.append(payload)
    if isinstance(payload, dict):
        candidate_result = payload.get("candidate_result")
        source_execution = candidate_result.get("source_execution") if isinstance(candidate_result, dict) else None
        if isinstance(source_execution, dict) and _operator_execution_matches_packet_manuscript(source_execution, packet_sha):
            payloads.append(source_execution)
    attempts: list[dict[str, Any]] = []
    for payload_item in payloads:
        for attempt in payload_item.get("attempts") or []:
            if isinstance(attempt, dict) and attempt.get("gate_passed") is not True:
                attempts.append(attempt)
    return attempts
