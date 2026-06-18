from __future__ import annotations

from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.feedback.packet_records import _artifact_by_role


_HUMAN_NEEDED_CONTEXT_ROLES = ("qa_loop_plan", "qa_loop_execution", "operator_feedback_execution")


def _packet_has_human_needed_context(packet: dict[str, Any]) -> bool:
    for role in _HUMAN_NEEDED_CONTEXT_ROLES:
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
