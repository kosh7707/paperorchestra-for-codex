from __future__ import annotations

from typing import Any


def _numeric_axis_scores(axis_scores: Any) -> dict[str, float]:
    if not isinstance(axis_scores, dict):
        return {}
    return {
        key: value.get("score")
        for key, value in axis_scores.items()
        if isinstance(value, dict) and isinstance(value.get("score"), (int, float))
    }


def _axis_presence(axis_scores: Any, expected_axes: list[str]) -> tuple[list[str], list[str], list[str]]:
    present_axes = list(axis_scores.keys()) if isinstance(axis_scores, dict) else []
    missing_axes = [axis for axis in expected_axes if axis not in present_axes]
    extra_axes = [axis for axis in present_axes if axis not in expected_axes]
    return present_axes, missing_axes, extra_axes
