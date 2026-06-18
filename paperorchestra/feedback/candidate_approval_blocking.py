from __future__ import annotations

from typing import Any

_HARD_APPROVAL_ROLLBACK_REASONS = {
    "tier2_claim_safety_new_failures",
    "active_tier2_metric_regression",
    "repeated_non_promotable_candidate",
    "citation_integrity_failed",
    "citation_integrity_audit_fail",
    "citation_source_match_fail",
    "claim_source_mismatch",
}
_ALLOWED_NEW_TIER2_FAILURES = {"citation_support_manual_check"}


def _nested_candidate_approval_is_blocked(payload: dict[str, Any]) -> bool:
    """Return true when a nested approval is evidence of a failed approval attempt."""

    if isinstance(payload.get("candidate_approval"), dict):
        return False
    candidate_result = payload.get("candidate_result")
    if not isinstance(candidate_result, dict) or not isinstance(candidate_result.get("candidate_approval"), dict):
        return False
    for attempt in payload.get("attempts") or []:
        if not isinstance(attempt, dict):
            continue
        reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
        new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
        if reasons & _HARD_APPROVAL_ROLLBACK_REASONS:
            return True
        if new_tier2 - _ALLOWED_NEW_TIER2_FAILURES:
            return True
    return str(payload.get("promotion_status") or "") == "rolled_back"
