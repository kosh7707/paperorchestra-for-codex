from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json
from paperorchestra.feedback import operator_answer_metadata as _answer_metadata
from paperorchestra.feedback import operator_issue_contract as _issues
from paperorchestra.feedback.operator_contract_constants import (
    OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION,
    OPERATOR_PACKET_SCHEMA_VERSION,
)
from paperorchestra.feedback.packet_artifacts import _file_sha256, _packet_sha256


def _read_packet(path: str | Path) -> dict[str, Any]:
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise ContractError("operator review packet must be a JSON object")
    if packet.get("schema_version") != OPERATOR_PACKET_SCHEMA_VERSION:
        raise ContractError("operator review packet has an unsupported schema_version")
    expected = _packet_sha256(packet)
    if packet.get("packet_sha256") != expected:
        raise ContractError("operator review packet hash does not match packet contents")
    for artifact in packet.get("artifacts") or []:
        if not isinstance(artifact, dict):
            raise ContractError("operator review packet artifact entry must be an object")
        actual = _file_sha256(artifact.get("path"))
        if not actual or actual != artifact.get("sha256"):
            raise ContractError(f"operator review packet artifact is missing or stale: {artifact.get('role')}")
    return packet


def _load_imported_feedback(imported_feedback_path: str | Path) -> dict[str, Any]:
    payload = read_json(imported_feedback_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION:
        raise ContractError("imported operator feedback has an unsupported schema_version")
    if payload.get("source") != _issues.OPERATOR_SOURCE or payload.get("not_independent_human_review") is not True:
        raise ContractError("imported operator feedback lost non-independent provenance")
    packet = _read_packet(payload.get("packet_path"))
    if payload.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("imported operator feedback packet hash is stale")
    if "human_needed_answer" in payload:
        _answer_metadata._validate_human_needed_answer_metadata(
            payload.get("human_needed_answer"),
            packet,
            {str(issue.get("id") or "") for issue in payload.get("issues") or [] if isinstance(issue, dict)},
            packet_path=payload.get("packet_path"),
            intent=str(payload.get("intent") or ""),
            imported_issue_roles={
                str(issue.get("source_artifact_role") or "")
                for issue in payload.get("issues") or []
                if isinstance(issue, dict)
            },
        )
    if "operator_review_notes" in payload:
        _answer_metadata.validate_operator_review_notes(payload.get("operator_review_notes"))
    return payload
