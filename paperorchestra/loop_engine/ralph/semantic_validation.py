from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.state import _read_json


def _validation_failing_codes_from_repair(repair: dict[str, Any]) -> list[str]:
    validation = repair.get("validation") if isinstance(repair.get("validation"), dict) else {}
    path = validation.get("path") if isinstance(validation, dict) else None
    payload = _read_json(path) if path else None
    issues = payload.get("issues") if isinstance(payload, dict) and isinstance(payload.get("issues"), list) else []
    codes = [str(issue.get("code")) for issue in issues if isinstance(issue, dict) and issue.get("code")]
    if not codes and isinstance(validation, dict) and validation.get("ok") is False:
        codes.append("validation_failed")
    return sorted(dict.fromkeys(codes))
