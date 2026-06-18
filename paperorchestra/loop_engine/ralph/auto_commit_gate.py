from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.auto_commit_metrics import _active_metric_regressions
from paperorchestra.loop_engine.ralph.state import quality_eval_status


def _auto_commit_progressive_citation_candidate(
    *,
    progress: dict[str, Any],
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    require_compile: bool,
    before_quality_eval: dict[str, Any] | None,
    after_quality_eval: dict[str, Any] | None,
    after_codes: set[str],
    residual_citation_failures: list[str],
) -> tuple[bool, str]:
    """Return whether a verified citation-repair candidate can stay canonical."""
    reason = _auto_commit_block_reason(
        progress=progress,
        validation_payload=validation_payload,
        compile_payload=compile_payload,
        require_compile=require_compile,
        before_quality_eval=before_quality_eval,
        after_quality_eval=after_quality_eval,
        residual_citation_failures=residual_citation_failures,
    )
    return (False, reason) if reason else (True, "strict_progress_without_new_failures")


def _auto_commit_block_reason(
    *,
    progress: dict[str, Any],
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    require_compile: bool,
    before_quality_eval: dict[str, Any] | None,
    after_quality_eval: dict[str, Any] | None,
    residual_citation_failures: list[str],
) -> str | None:
    if validation_payload.get("ok") is not True:
        return "validation_failed"
    if require_compile and (not isinstance(compile_payload, dict) or compile_payload.get("ok") is not True):
        return "compile_failed"
    if progress.get("forward_progress") is not True:
        return "no_forward_progress"
    if progress.get("new_codes"):
        return "new_failure_codes"
    tier_reason = _blocking_tier_reason(after_quality_eval)
    if tier_reason:
        return tier_reason
    if _active_metric_regressions(
        before_quality_eval,
        after_quality_eval,
        active_codes=[str(code) for code in progress.get("before_failing_codes") or []],
    ):
        return "active_tier2_metric_regression"
    if _non_human_reviewable_residuals(residual_citation_failures):
        return "non_human_reviewable_citation_support_residuals"
    return None


def _blocking_tier_reason(after_quality_eval: dict[str, Any] | None) -> str | None:
    after_statuses = quality_eval_status(after_quality_eval or {})
    if after_statuses.get("tier_0_preconditions") == "fail":
        return "tier0_failed"
    if after_statuses.get("tier_1_structural") == "fail":
        return "tier1_failed"
    return None


def _non_human_reviewable_residuals(residual_citation_failures: list[str]) -> list[str]:
    return sorted(
        code
        for code in residual_citation_failures
        if code not in {"citation_support_manual_check", "citation_support_weak"}
    )
