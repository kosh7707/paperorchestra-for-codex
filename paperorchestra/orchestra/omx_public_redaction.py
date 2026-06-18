from __future__ import annotations

from typing import Any


def _public_payload(value: Any) -> Any:
    if hasattr(value, "to_public_dict"):
        return value.to_public_dict()
    if isinstance(value, dict):
        return _jsonable_without_private_values(value)
    if isinstance(value, (list, tuple)):
        return [_public_payload(item) for item in value]
    return value


def _jsonable_without_private_values(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.startswith("private_") or key_text in {"raw_text", "prompt", "argv", "executable_command"}:
                result[key_text] = "<redacted>"
            else:
                result[key_text] = _jsonable_without_private_values(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_jsonable_without_private_values(item) for item in value]
    return value


def _public_input_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"topic", "rubric", "argv", "prompt", "raw_text"} or key.startswith("private_"):
            result[key] = "<redacted>"
        else:
            result[key] = value
    return result
