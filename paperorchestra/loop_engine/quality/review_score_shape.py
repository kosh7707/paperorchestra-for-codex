from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.policy import REQUIRED_REVIEW_AXES


def _nonempty_string(value: Any, *, min_len: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_len


def _review_shape_failures(review: dict[str, Any], *, quality_mode: str) -> list[str]:
    if quality_mode != "claim_safe":
        return []
    failures: list[str] = []
    if review.get("schema_version") != "paper-review/1":
        failures.append("review_schema_invalid")
    axis_scores = review.get("axis_scores")
    if not isinstance(axis_scores, dict) or set(axis_scores) != REQUIRED_REVIEW_AXES:
        failures.append("review_axes_incomplete")
    else:
        failures.extend(_axis_score_failures(axis_scores))
    summary = review.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("weaknesses"), list) or not isinstance(summary.get("top_improvements"), list):
        failures.append("review_summary_missing")
    if not isinstance(review.get("penalties"), list):
        failures.append("review_penalties_missing")
    return sorted(dict.fromkeys(failures))


def _axis_score_failures(axis_scores: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for axis in sorted(REQUIRED_REVIEW_AXES):
        payload = axis_scores.get(axis)
        score = payload.get("score") if isinstance(payload, dict) else payload
        justification = payload.get("justification") if isinstance(payload, dict) else None
        if not isinstance(score, (int, float)) or not (0 <= float(score) <= 100):
            failures.append("review_axis_invalid")
        if not _nonempty_string(justification, min_len=10):
            failures.append("review_axis_justification_missing")
    return failures
