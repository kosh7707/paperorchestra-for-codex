from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.reviews.source_support_resolution_paths import _human_resolution_path

_SUPPORTED_ACTIONS = {"provide_source_url", "replace_citation", "weaken_claim", "remove_claim"}


def _load_human_resolution(cwd: str | Path | None, case: dict[str, Any]) -> dict[str, Any] | None:
    path = _human_resolution_path(cwd, str(case.get("id") or ""))
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return {"action": "invalid", "status": "invalid", "reason": "unreadable_resolution"}
    return _validated_resolution_payload(payload, case)


def _validated_resolution_payload(payload: Any, case: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"action": "invalid", "status": "invalid", "reason": "invalid_resolution"}
    if payload.get("schema") != "citation-human-resolution/1":
        return {"action": "invalid", "status": "invalid", "reason": "invalid_schema"}
    if str(payload.get("case") or "") != str(case.get("id") or ""):
        return {"action": "invalid", "status": "invalid", "reason": "case_mismatch"}
    action = str(payload.get("action") or "").strip()
    if action not in _SUPPORTED_ACTIONS:
        return {"action": action or "invalid", "status": "invalid", "reason": "unsupported_action"}
    return payload
