from __future__ import annotations

from typing import Any

from paperorchestra.reviews.evaluation_constants import (
    EXPECTED_CITATION_STATISTICS_KEYS,
    EXPECTED_LITERATURE_REVIEW_AXES,
    EXPECTED_REVIEW_SUMMARY_KEYS,
)


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


def build_review_gate_payload(*, session_id: str, review_path: str | None, latest_review: Any) -> dict[str, Any]:
    axis_scores = latest_review.get("axis_scores") if isinstance(latest_review, dict) else {}
    present_axes, missing_axes, extra_axes = _axis_presence(axis_scores, EXPECTED_LITERATURE_REVIEW_AXES)
    citation_statistics = latest_review.get("citation_statistics") if isinstance(latest_review, dict) else {}
    summary = latest_review.get("summary") if isinstance(latest_review, dict) else {}
    questions = latest_review.get("questions") if isinstance(latest_review, dict) else []
    missing_citation_statistics_keys = _missing_keys(citation_statistics, EXPECTED_CITATION_STATISTICS_KEYS)
    missing_summary_keys = _missing_keys(summary, EXPECTED_REVIEW_SUMMARY_KEYS)
    questions_count = len(questions) if isinstance(questions, list) else 0
    overall_score = latest_review.get("overall_score") if isinstance(latest_review, dict) else None
    anti_inflation = _anti_inflation_violations(overall_score, _numeric_axis_scores(axis_scores))
    return {
        "session_id": session_id,
        "review_path": review_path,
        "overall_score": overall_score,
        "expected_axes": EXPECTED_LITERATURE_REVIEW_AXES,
        "present_axes": present_axes,
        "missing_axes": missing_axes,
        "extra_axes": extra_axes,
        "overlap_count": len(present_axes) - len(extra_axes),
        "has_citation_statistics": isinstance(latest_review, dict) and isinstance(citation_statistics, dict),
        "has_penalties": isinstance(latest_review, dict) and isinstance(latest_review.get("penalties"), list),
        "has_summary": isinstance(latest_review, dict) and isinstance(summary, dict),
        "has_questions": isinstance(latest_review, dict) and isinstance(questions, list),
        "missing_citation_statistics_keys": missing_citation_statistics_keys,
        "missing_summary_keys": missing_summary_keys,
        "questions_count": questions_count,
        "anti_inflation_violations": anti_inflation,
        "comparability_status": _comparability_status(
            latest_review=latest_review,
            missing_axes=missing_axes,
            missing_citation_statistics_keys=missing_citation_statistics_keys,
            missing_summary_keys=missing_summary_keys,
            questions_count=questions_count,
            anti_inflation_violations=anti_inflation,
        ),
        "notes": [
            "This artifact checks whether the current review surface matches the expected AgentReview-style literature-review autorater structure.",
        ],
    }


def _missing_keys(value: Any, expected_keys: list[str]) -> list[str]:
    return [key for key in expected_keys if key not in value] if isinstance(value, dict) else expected_keys[:]
