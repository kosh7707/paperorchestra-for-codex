from __future__ import annotations

from typing import Any

JSON = dict[str, Any]


def _schema(properties: JSON, required: list[str] | None = None) -> JSON:
    schema: JSON = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema
