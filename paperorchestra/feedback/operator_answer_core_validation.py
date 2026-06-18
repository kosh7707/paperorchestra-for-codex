from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_answer_constants import (
    HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS,
    HUMAN_NEEDED_HANDOFF_TYPES,
    HUMAN_NEEDED_METADATA_ALLOWED_KEYS,
    OPERATOR_FEEDBACK_INTENTS,
)
from paperorchestra.feedback.operator_answer_redaction import _contains_forbidden_human_needed_metadata
from paperorchestra.feedback.packet_artifacts import _file_sha256


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
