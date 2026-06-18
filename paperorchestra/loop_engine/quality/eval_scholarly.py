from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.eval_tiers import _status_from_failures, _tier
from paperorchestra.loop_engine.quality.policy import MODE_THRESHOLDS
from paperorchestra.loop_engine.quality.reviews import (
    _review_score_check,
    _reviewer_independence_check,
    _section_quality_check,
)


def build_scholarly_quality_tier(*, cwd: str | Path | None, state, mode: str) -> dict[str, Any]:
    review_check = _review_score_check(state, quality_mode=mode)
    section_check = _section_quality_check(cwd, state, quality_mode=mode)
    reviewer_independence = _reviewer_independence_check(cwd, state, quality_mode=mode)
    thresholds = MODE_THRESHOLDS[mode]
    tier3_failing: list[str] = []
    tier3_failing.extend(review_check.get("failing_codes") or [])
    tier3_failing.extend(section_check.get("failing_codes") or [])
    tier3_failing.extend(reviewer_independence.get("failing_codes") or [])
    overall_score = review_check.get("overall_score")
    axis_scores = review_check.get("axis_scores") if isinstance(review_check.get("axis_scores"), dict) else {}
    anti = review_check.get("anti_inflation_violations") or []
    return _tier(
        status=_status_from_failures(tier3_failing, warn_only=True),
        checks={
            "scorecard_available": {
                "status": "pass" if review_check.get("status") == "pass" else "warn",
                "source": review_check.get("path"),
            },
            "review_scorecard": review_check,
            "section_quality_critic": section_check,
            "reviewer_independence": reviewer_independence,
            "thresholds": thresholds,
            "writer_score_visibility": {"status": "pass", "writer_receives_scores": False, "operator_only": True},
        },
        failing_codes=tier3_failing,
        overall_score=overall_score,
        axis_scores=axis_scores,
        anti_inflation_triggered=bool(review_check.get("anti_inflation_triggered")),
        anti_inflation_violations=anti,
    )
