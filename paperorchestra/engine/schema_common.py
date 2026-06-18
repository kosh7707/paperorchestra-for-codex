from __future__ import annotations

from typing import Any


VALID_ASPECT_RATIOS = {"1:1", "1:4", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
VALID_PLOT_TYPES = {"plot", "diagram"}


def _closed_object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required or list(properties.keys()),
        "properties": properties,
    }


def _string_list_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}
