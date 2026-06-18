from __future__ import annotations

from typing import Any


def _mark_invalid_human_resolution(case: dict[str, Any], resolution: dict[str, Any]) -> None:
    case["resolution"] = resolution
    case["_skip_source_resolution"] = True
    case["evidence"] = {"status": "missing", "why": str(resolution.get("reason") or "invalid_resolution")}
    case["verdict"] = "human_needed"
    case["ask"] = "Fix artifacts/references/{}/human-resolution.json or provide source.pdf/html/txt.".format(case.get("id"))
