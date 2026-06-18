from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.history_failures import (
    _history_entry_consumes_budget,
    _repeated_actionable_failure,
)
from paperorchestra.loop_engine.quality.history_io import _read_quality_history


def _resolve_axis_drop_tolerance(default: float = 0.0) -> float:
    raw = os.environ.get("PAPERO_QA_LOOP_AXIS_DROP_TOLERANCE")
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _build_cross_iteration(
    cwd: str | Path | None,
    session_id: str | None,
    manuscript_hash: str | None,
    current_failing_codes: list[str],
    max_iterations: int,
    *,
    current_axis_scores: dict[str, float] | None = None,
    current_attempt_consumes_budget: bool = False,
) -> dict[str, Any]:
    history = [entry for entry in _read_quality_history(cwd) if not session_id or entry.get("session_id") == session_id]
    budget_history = [entry for entry in history if _history_entry_consumes_budget(entry)]
    attempts_used_before = len(budget_history)
    attempts_used = attempts_used_before + (1 if current_attempt_consumes_budget else 0)
    iteration_index = attempts_used if current_attempt_consumes_budget else attempts_used + 1
    previous = budget_history[-1] if budget_history else None
    previous_codes = set(previous.get("failing_codes") or []) if isinstance(previous, dict) else set()
    current_codes = set(current_failing_codes)
    previous_axes = (
        previous.get("tier_3_axis_scores")
        if isinstance(previous, dict) and isinstance(previous.get("tier_3_axis_scores"), dict)
        else {}
    )
    current_axes = current_axis_scores or {}
    axis_drops = _tier_3_axis_drops(previous_axes, current_axes, tolerance=_resolve_axis_drop_tolerance())
    oscillation_detected = False
    flapping_codes: list[str] = []
    if len(budget_history) >= 2:
        two_back = set(budget_history[-2].get("failing_codes") or [])
        one_back = set(budget_history[-1].get("failing_codes") or [])
        if current_codes == two_back and current_codes != one_back:
            oscillation_detected = True
            flapping_codes = sorted(current_codes | one_back)
    same_manuscript_as_previous = bool(previous and manuscript_hash and previous.get("manuscript_hash") == manuscript_hash)
    forward_progress = not (bool(current_codes) and current_codes == previous_codes)
    if same_manuscript_as_previous and current_codes:
        forward_progress = False
    return {
        "iteration_index": iteration_index,
        "budget": {
            "max": max_iterations,
            "remaining": max(max_iterations - attempts_used, 0),
            "attempts_used": attempts_used,
            "attempts_used_before_current": attempts_used_before,
            "current_attempt_consumes_budget": current_attempt_consumes_budget,
        },
        "regression": {
            "vs_previous_manuscript_hash": previous.get("manuscript_hash") if isinstance(previous, dict) else None,
            "same_manuscript_as_previous": same_manuscript_as_previous,
            "new_failing_codes": sorted(current_codes - previous_codes),
            "resolved_failing_codes": sorted(previous_codes - current_codes),
            "tier_3_axis_drops": axis_drops,
            "oscillation": {"detected": oscillation_detected, "flapping_codes": flapping_codes},
            "forward_progress": forward_progress,
            "repeated_actionable_failure": _repeated_actionable_failure(budget_history),
        },
    }


def _tier_3_axis_drops(
    previous_axes: dict[str, Any],
    current_axes: dict[str, float],
    *,
    tolerance: float,
) -> list[dict[str, Any]]:
    axis_drops: list[dict[str, Any]] = []
    for axis, previous_score in previous_axes.items():
        current_score = current_axes.get(axis)
        if isinstance(previous_score, (int, float)) and isinstance(current_score, (int, float)):
            drop = float(previous_score) - float(current_score)
            if drop > tolerance:
                axis_drops.append(
                    {
                        "axis": axis,
                        "previous": float(previous_score),
                        "current": float(current_score),
                        "drop": round(drop, 4),
                        "tolerance": tolerance,
                    }
                )
    return axis_drops
