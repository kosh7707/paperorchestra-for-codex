from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.operator_answer_constants import (
    HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
)
from paperorchestra.feedback.operator_answer_core_validation import (
    _validate_decision_kind,
    _validate_digest_fields,
    _validate_handoff_type,
    _validate_metadata_shape,
    _validate_packet_binding,
)
from paperorchestra.feedback.operator_answer_target_validation import (
    _validate_selected_handoff_source,
    _validate_target_action_id,
    _validate_target_issue_ids,
)


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
