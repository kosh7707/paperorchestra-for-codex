from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_contract import (
    AXIS_CATASTROPHIC_DROP,
    HUMAN_REVIEWABLE_NEW_TIER2_CODES,
    OVERALL_CATASTROPHIC_DROP,
)
from paperorchestra.feedback.operator_metric_delta import _active_tier2_metric_delta
from paperorchestra.feedback.operator_quality_codes import _tier_status


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
    _append_text_change_reasons(reasons, manuscript_changed=manuscript_changed, candidate_result=candidate_result)
    _append_static_gate_reasons(reasons, validation_payload=validation_payload, compile_payload=compile_payload, quality_eval=quality_eval)
    _append_tier2_regression_reasons(
        reasons,
        quality_eval=quality_eval,
        base_quality_eval=base_quality_eval,
        quality_mode=quality_mode,
        candidate_result=candidate_result,
        new_tier2_failures=new_tier2_failures,
        base_active_failures=base_active_failures,
        resolved_active_failures=resolved_active_failures,
        allow_human_reviewable_new_tier2=allow_human_reviewable_new_tier2,
        protected_supported_citation_regressions=protected_supported_citation_regressions,
    )
    if require_issue_progress and not any(item["status"] in {"reflected", "partially_reflected"} for item in incorporation):
        reasons.append("issue_progress_missing")
    if _catastrophic_review_regression(candidate_result):
        reasons.append("reviewer_catastrophic_regression")
    return not reasons, reasons


def _append_text_change_reasons(reasons: list[str], *, manuscript_changed: bool, candidate_result: dict[str, Any] | None) -> None:
    if manuscript_changed:
        return
    reasons.append("no_textual_change")
    failure_category = str((candidate_result or {}).get("executor_failure_category") or "none")
    reasons.append("executor_crashed" if failure_category != "none" else "executor_returned_identical_content")


def _append_static_gate_reasons(
    reasons: list[str],
    *,
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    quality_eval: dict[str, Any],
) -> None:
    if not validation_payload.get("ok"):
        reasons.append("validation_failed")
    if compile_payload and not compile_payload.get("ok"):
        reasons.append("compile_failed")
    if _tier_status(quality_eval, "tier_0_preconditions") == "fail":
        reasons.append("tier0_failed")
    if _tier_status(quality_eval, "tier_1_structural") == "fail":
        reasons.append("tier1_failed")


def _append_tier2_regression_reasons(
    reasons: list[str],
    *,
    quality_eval: dict[str, Any],
    base_quality_eval: dict[str, Any] | None,
    quality_mode: str,
    candidate_result: dict[str, Any] | None,
    new_tier2_failures: list[str],
    base_active_failures: list[str],
    resolved_active_failures: list[str],
    allow_human_reviewable_new_tier2: bool,
    protected_supported_citation_regressions: list[dict[str, Any]] | None,
) -> None:
    hard_new_tier2_failures = [
        code
        for code in new_tier2_failures
        if not (allow_human_reviewable_new_tier2 and code in HUMAN_REVIEWABLE_NEW_TIER2_CODES)
    ]
    if quality_mode == "claim_safe" and hard_new_tier2_failures:
        reasons.append("tier2_claim_safety_new_failures")
    metric_delta = _active_tier2_metric_delta(
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
