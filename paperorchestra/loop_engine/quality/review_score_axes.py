from __future__ import annotations

from typing import Any


def _numeric_axis_scores(review: dict[str, Any]) -> dict[str, float]:
    axes: dict[str, float] = {}
    axis_scores = review.get("axis_scores") if isinstance(review, dict) else {}
    if isinstance(axis_scores, dict):
        for axis, value in axis_scores.items():
            score = value.get("score") if isinstance(value, dict) else value
            if isinstance(score, (int, float)):
                axes[str(axis)] = float(score)
    return axes


def _anti_inflation_violations(overall_score: float | None, axis_scores: dict[str, float]) -> list[str]:
    violations: list[str] = []
    if overall_score is None:
        return violations
    if any(score < 50 for score in axis_scores.values()) and overall_score > 75:
        violations.append("overall_score_above_75_with_sub50_axis")
    if overall_score > 90:
        violations.append("overall_score_above_90_requires_exceptional_evidence")
    critical_score = axis_scores.get("critical_analysis_and_synthesis")
    if critical_score is not None and critical_score > 60 and overall_score <= 55:
        violations.append("critical_analysis_above_60_with_low_overall_score")
    return violations
