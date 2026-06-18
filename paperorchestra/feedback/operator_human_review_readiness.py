from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.feedback.operator_contract import HUMAN_REVIEWABLE_NEW_TIER2_CODES

_DISQUALIFYING_GATE_REASONS = {
    "no_textual_change",
    "executor_crashed",
    "executor_returned_identical_content",
    "validation_failed",
    "compile_failed",
    "tier0_failed",
    "tier1_failed",
    "active_blocker_metric_progress_missing",
    "active_blocker_progress_missing",
    "active_tier2_metric_regression",
    "protected_supported_citation_regression",
    "issue_progress_missing",
    "repeated_non_promotable_candidate",
    "reviewer_catastrophic_regression",
}


def _candidate_attempt_ready_for_human_review(attempt: dict[str, Any]) -> bool:
    if not attempt.get("resolved_active_failures"):
        return False
    candidate_path = attempt.get("candidate_path")
    if not candidate_path or not Path(str(candidate_path)).exists():
        return False
    reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
    if reasons & _DISQUALIFYING_GATE_REASONS:
        return False
    new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
    return new_tier2 <= HUMAN_REVIEWABLE_NEW_TIER2_CODES


def _best_human_review_candidate_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [attempt for attempt in attempts if _candidate_attempt_ready_for_human_review(attempt)]
    if not candidates:
        return None
    return max(candidates, key=_human_review_candidate_score)


def _human_review_candidate_score(attempt: dict[str, Any]) -> tuple[int, int, int]:
    return (
        len(attempt.get("resolved_active_failures") or []),
        -len(attempt.get("candidate_active_failures") or []),
        -int(attempt.get("attempt_index") or 0),
    )
