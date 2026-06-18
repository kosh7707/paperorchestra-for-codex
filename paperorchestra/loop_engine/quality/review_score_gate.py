from __future__ import annotations

from typing import Any

from .policy import MODE_THRESHOLDS
from .review_score_provenance import _review_provenance_failures
from .review_score_shape import _review_shape_failures
from .utils import _file_sha256, _read_json_if_exists


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


def _latest_review_payload(state) -> tuple[str | None, dict[str, Any] | None]:
    if state.artifacts.latest_review_json:
        payload = _read_json_if_exists(state.artifacts.latest_review_json)
        if isinstance(payload, dict):
            return state.artifacts.latest_review_json, payload
    if state.review_history:
        raw_path = state.review_history[-1].raw_path
        payload = _read_json_if_exists(raw_path)
        if isinstance(payload, dict):
            return raw_path, payload
    return None, None


def _review_score_check(state, *, quality_mode: str) -> dict[str, Any]:
    path, review = _latest_review_payload(state)
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if not isinstance(review, dict):
        return {
            "status": "fail",
            "path": path,
            "failing_codes": ["review_score_missing"],
            "overall_score": None,
            "axis_scores": {},
            "anti_inflation_triggered": False,
            "anti_inflation_violations": [],
        }
    shape_failures = _review_shape_failures(review, quality_mode=quality_mode)
    provenance_failures, provenance_check = _review_provenance_failures(
        review,
        current_sha=current_sha,
        quality_mode=quality_mode,
    )
    if not review.get("manuscript_sha256"):
        return {
            "status": "fail",
            "path": path,
            "failing_codes": sorted(dict.fromkeys(["review_score_legacy_untrusted"] + shape_failures + provenance_failures)),
            "overall_score": review.get("overall_score"),
            "axis_scores": _numeric_axis_scores(review),
            "anti_inflation_triggered": False,
            "anti_inflation_violations": [],
            "provenance": provenance_check,
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": review.get("manuscript_sha256"),
        }
    if current_sha and review.get("manuscript_sha256") != current_sha:
        return {
            "status": "fail",
            "path": path,
            "failing_codes": sorted(dict.fromkeys(["review_score_stale"] + shape_failures + provenance_failures)),
            "overall_score": review.get("overall_score"),
            "axis_scores": _numeric_axis_scores(review),
            "anti_inflation_triggered": False,
            "anti_inflation_violations": [],
            "provenance": provenance_check,
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": review.get("manuscript_sha256"),
        }
    thresholds = MODE_THRESHOLDS[quality_mode]
    raw_overall = review.get("overall_score")
    overall_score = float(raw_overall) if isinstance(raw_overall, (int, float)) else None
    axis_scores = _numeric_axis_scores(review)
    anti = _anti_inflation_violations(overall_score, axis_scores)
    failing_codes: list[str] = []
    failing_codes.extend(shape_failures)
    failing_codes.extend(provenance_failures)
    if overall_score is None:
        failing_codes.append("review_score_missing")
    elif overall_score < thresholds["overall_min"]:
        failing_codes.append("review_overall_below_threshold")
    if axis_scores and min(axis_scores.values()) < thresholds["axis_min"]:
        failing_codes.append("review_axis_below_threshold")
    if anti:
        failing_codes.append("review_anti_inflation")
    return {
        "status": "fail" if failing_codes else "pass",
        "path": path,
        "failing_codes": failing_codes,
        "overall_score": overall_score,
        "axis_scores": axis_scores,
        "anti_inflation_triggered": bool(anti),
        "anti_inflation_violations": anti,
        "provenance": provenance_check,
        "expected_manuscript_sha256": current_sha,
        "actual_manuscript_sha256": review.get("manuscript_sha256"),
    }
