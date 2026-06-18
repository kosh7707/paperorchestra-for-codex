from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary_patterns import control_prose_markers


def _walk_strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        found: list[tuple[str, str]] = []
        for key, child in value.items():
            found.extend(_walk_strings(child, f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value):
            found.extend(_walk_strings(child, f"{path}[{index}]"))
        return found
    return []


def author_facing_payload_markers(payload: Any) -> list[dict[str, str]]:
    markers: list[dict[str, str]] = []
    for path, text in _walk_strings(payload):
        for marker in control_prose_markers(text):
            markers.append({"path": path, "marker": marker})
    return markers


def assert_author_facing_payload(payload: Any, *, label: str = "author-facing payload") -> None:
    markers = author_facing_payload_markers(payload)
    if markers:
        details = ", ".join(f"{item['path']}:{item['marker']}" for item in markers[:8])
        raise ValueError(f"{label} contains machine/control prose markers: {details}")
