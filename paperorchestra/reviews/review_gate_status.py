from __future__ import annotations

from typing import Any


def _anti_inflation_violations(overall_score: Any, numeric_axis_scores: dict[str, float]) -> list[str]:
    violations: list[str] = []
    if isinstance(overall_score, (int, float)):
        if any(isinstance(score, (int, float)) and score < 50 for score in numeric_axis_scores.values()) and overall_score > 75:
            violations.append("overall_score_above_75_with_sub50_axis")
        if overall_score > 90:
            violations.append("overall_score_above_90_requires_exceptional_evidence")
    critical_score = numeric_axis_scores.get("critical_analysis_and_synthesis")
    if isinstance(critical_score, (int, float)) and critical_score > 60 and isinstance(overall_score, (int, float)) and overall_score <= 55:
        violations.append("critical_analysis_above_60_with_low_overall_score")
    return violations


def _comparability_status(
    *,
    latest_review: Any,
    missing_axes: list[str],
    missing_citation_statistics_keys: list[str],
    missing_summary_keys: list[str],
    questions_count: int,
    anti_inflation_violations: list[str],
) -> str:
    if (
        not missing_axes
        and not missing_citation_statistics_keys
        and not missing_summary_keys
        and isinstance(latest_review, dict)
        and isinstance(latest_review.get("penalties"), list)
        and questions_count > 0
        and not anti_inflation_violations
    ):
        return "implemented"
    return "partial" if latest_review else "missing"
