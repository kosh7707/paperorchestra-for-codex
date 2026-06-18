from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_candidate_packets import _packet_artifact_payload

_CANDIDATE_APPROVAL_SOURCE_ROLES = frozenset({"qa_loop_execution", "operator_feedback_execution"})


def _candidate_approval_source_role(imported: dict[str, Any]) -> str | None:
    roles = {
        str(issue.get("source_artifact_role") or "")
        for issue in imported.get("issues") or []
        if isinstance(issue, dict) and str(issue.get("source_artifact_role") or "") in _CANDIDATE_APPROVAL_SOURCE_ROLES
    }
    if len(roles) > 1:
        raise ContractError("approve_existing_candidate feedback must target exactly one candidate approval source artifact")
    return next(iter(roles), None)


def _candidate_source_execution_from_packet(packet: dict[str, Any], preferred_role: str | None = None) -> tuple[dict[str, Any], str]:
    roles = (preferred_role,) if preferred_role else ("qa_loop_execution", "operator_feedback_execution")
    for role in roles:
        if role not in _CANDIDATE_APPROVAL_SOURCE_ROLES:
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
