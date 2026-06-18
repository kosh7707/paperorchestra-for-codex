from __future__ import annotations

from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.feedback.packet_records import _artifact_by_role


def _packet_payload_by_role(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None
