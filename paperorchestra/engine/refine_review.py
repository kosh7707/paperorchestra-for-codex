from __future__ import annotations

import os
from typing import Any


def _redact_review_scores_for_writer(review_payload: dict[str, Any]) -> dict[str, Any]:
    """Remove numeric reviewer scores before feeding critique back to a writer/refiner.

    The acceptance gate still uses scores internally after the candidate is
    produced, but the generative writer should optimize against structured
    issues, not the reviewer scorecard itself.
    """
    redacted = dict(review_payload)
    redacted.pop("overall_score", None)
    redacted.pop("axis_scores", None)
    redacted["score_redaction"] = {
        "overall_score_removed": "writer_blind_to_reviewer_scores",
        "axis_scores_removed": "writer_blind_to_reviewer_scores",
    }
    return redacted


def _accept_review_delta(
    candidate_score: float,
    previous_score: float,
    candidate_axes: dict[str, float],
    previous_axes: dict[str, float],
) -> bool:
    if candidate_score < previous_score:
        return False
    raw_tolerance = os.environ.get("PAPERO_REFINE_AXIS_TOLERANCE")
    try:
        tolerance = max(0.0, float(raw_tolerance)) if raw_tolerance is not None else 0.0
    except ValueError:
        tolerance = 0.0
    keys = set(candidate_axes) & set(previous_axes)
    return not keys or all(candidate_axes.get(key, 0.0) >= previous_axes.get(key, 0.0) - tolerance for key in keys)
