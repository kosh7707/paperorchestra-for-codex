from __future__ import annotations

from typing import Any

from paperorchestra.feedback import operator_metrics as _metrics
from paperorchestra.feedback.operator_human_review import (
    _attach_candidate_approval_from_attempt,
    _best_human_review_candidate_attempt,
)
from paperorchestra.feedback.operator_contract import (
    AXIS_CATASTROPHIC_DROP,
    HUMAN_REVIEWABLE_NEW_TIER2_CODES,
    OVERALL_CATASTROPHIC_DROP,
)


def _quality_failing_codes(quality_eval: dict[str, Any]) -> list[str]:
    result: list[str] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return result
    for tier in tiers.values():
        if isinstance(tier, dict) and tier.get("status") in {"fail", "warn"}:
            result.extend(str(code) for code in tier.get("failing_codes") or [])
    return sorted(dict.fromkeys(result))


def _tier_failing_codes(quality_eval: dict[str, Any] | None, tier_name: str) -> list[str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
    if not isinstance(tier, dict):
        return []
    return sorted(dict.fromkeys(str(code) for code in tier.get("failing_codes") or []))


def _tier_status(quality_eval: dict[str, Any], tier_name: str) -> str:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
    return str(tier.get("status") or "pass") if isinstance(tier, dict) else "pass"


def _candidate_hard_gate(
    *,
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    quality_eval: dict[str, Any],
    base_quality_eval: dict[str, Any] | None = None,
    quality_mode: str,
    incorporation: list[dict[str, Any]],
    candidate_result: dict[str, Any] | None,
    require_issue_progress: bool,
    manuscript_changed: bool,
    new_tier2_failures: list[str],
    base_active_failures: list[str],
    resolved_active_failures: list[str],
    allow_human_reviewable_new_tier2: bool = False,
    protected_supported_citation_regressions: list[dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not manuscript_changed:
        reasons.append("no_textual_change")
        failure_category = str((candidate_result or {}).get("executor_failure_category") or "none")
        if failure_category != "none":
            reasons.append("executor_crashed")
        else:
            reasons.append("executor_returned_identical_content")
    if not validation_payload.get("ok"):
        reasons.append("validation_failed")
    if compile_payload and not compile_payload.get("ok"):
        reasons.append("compile_failed")
    if _tier_status(quality_eval, "tier_0_preconditions") == "fail":
        reasons.append("tier0_failed")
    if _tier_status(quality_eval, "tier_1_structural") == "fail":
        reasons.append("tier1_failed")
    hard_new_tier2_failures = [
        code
        for code in new_tier2_failures
        if not (allow_human_reviewable_new_tier2 and code in HUMAN_REVIEWABLE_NEW_TIER2_CODES)
    ]
    if quality_mode == "claim_safe" and hard_new_tier2_failures:
        reasons.append("tier2_claim_safety_new_failures")
    metric_delta = _metrics._active_tier2_metric_delta(
        base_quality_eval,
        quality_eval,
        base_active_failures=base_active_failures,
    )
    if metric_delta.get("regressions"):
        reasons.append("active_tier2_metric_regression")
    if protected_supported_citation_regressions:
        reasons.append("protected_supported_citation_regression")
    metric_progress = bool(metric_delta.get("total_improved"))
    if (
        base_active_failures
        and not resolved_active_failures
        and not _candidate_reduces_citation_issue_count(candidate_result)
        and not metric_progress
    ):
        reasons.append("active_blocker_metric_progress_missing")
    if require_issue_progress and not any(item["status"] in {"reflected", "partially_reflected"} for item in incorporation):
        reasons.append("issue_progress_missing")
    if _catastrophic_review_regression(candidate_result):
        reasons.append("reviewer_catastrophic_regression")
    return not reasons, reasons


def _candidate_reduces_citation_issue_count(candidate_result: dict[str, Any] | None) -> bool:
    progress = candidate_result.get("candidate_progress") if isinstance(candidate_result, dict) else None
    if not isinstance(progress, dict):
        return False
    citation_issue_delta = progress.get("citation_issue_delta")
    return progress.get("forward_progress") is True and isinstance(citation_issue_delta, int) and citation_issue_delta < 0



def _catastrophic_review_regression(candidate_result: dict[str, Any] | None) -> bool:
    if not candidate_result:
        return False
    before = candidate_result.get("score_before")
    after = candidate_result.get("score_after")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and float(after) < float(before) - OVERALL_CATASTROPHIC_DROP:
        return True
    before_axes = candidate_result.get("axis_scores_before") or {}
    after_axes = candidate_result.get("axis_scores_after") or {}
    if isinstance(before_axes, dict) and isinstance(after_axes, dict):
        for key in set(before_axes) & set(after_axes):
            if isinstance(before_axes.get(key), (int, float)) and isinstance(after_axes.get(key), (int, float)):
                if float(after_axes[key]) < float(before_axes[key]) - AXIS_CATASTROPHIC_DROP:
                    return True
    return False
