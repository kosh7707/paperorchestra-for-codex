from __future__ import annotations

from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.feedback.packet_records import _artifact_by_role


def _load_artifact_payload(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _human_needed_actions(packet: dict[str, Any]) -> list[dict[str, Any]]:
    plan = _load_artifact_payload(packet, "qa_loop_plan")
    if not isinstance(plan, dict):
        return []
    return [
        action
        for action in plan.get("repair_actions") or []
        if isinstance(action, dict) and str(action.get("automation") or "") == "human_needed"
    ]
