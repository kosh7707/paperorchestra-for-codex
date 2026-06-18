from __future__ import annotations

from typing import Any


def _artifact_by_role(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    for artifact in packet.get("artifacts") or []:
        if isinstance(artifact, dict) and artifact.get("role") == role:
            return artifact
    return None
