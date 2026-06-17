from __future__ import annotations

from typing import Any

from .state import quality_eval_status


def _qa_loop_int_metric(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _qa_loop_tier2_metric_counts(quality_eval: dict[str, Any] | None) -> dict[str, int]:
    """Return generic Tier-2 issue counts for candidate auto-commit guards."""

    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers, dict) else {}
    checks = tier2.get("checks") if isinstance(tier2, dict) else {}
    metrics: dict[str, int] = {}
    support = checks.get("citation_support_critic") if isinstance(checks, dict) else None
    if isinstance(support, dict):
        summary = support.get("canonical_summary") or support.get("summary") or {}
        for code, count_field, summary_field in [
            ("citation_support_unsupported", "unsupported_count", "unsupported"),
            ("citation_support_contradicted", "contradicted_count", "contradicted"),
            ("citation_support_weak", "weakly_supported_count", "weakly_supported"),
            ("citation_support_manual_check", "needs_manual_check_count", "needs_manual_check"),
            ("citation_support_metadata_only", "metadata_only_count", "metadata_only"),
            ("citation_support_insufficient_evidence", "insufficient_evidence_count", "insufficient_evidence"),
            ("citation_support_evidence_missing", "evidence_missing_count", "evidence_missing"),
        ]:
            value = _qa_loop_int_metric(support.get(count_field))
            if value is None and isinstance(summary, dict):
                value = _qa_loop_int_metric(summary.get(summary_field))
            if value is not None:
                metrics[code] = value
    citation_quality = checks.get("citation_quality_gate") if isinstance(checks, dict) else None
    if isinstance(citation_quality, dict):
        counts = citation_quality.get("counts") if isinstance(citation_quality.get("counts"), dict) else {}
        for code, field in [
            ("citation_duplicate_support", "duplicate_reference_count"),
            ("citation_bomb_detected", "citation_bomb_count"),
            ("critical_citation_support_missing", "critical_need_count"),
            ("critical_unsupported_citation", "critical_unsupported_count"),
        ]:
            value = _qa_loop_int_metric(counts.get(field))
            if value is not None:
                metrics.setdefault(code, value)
    high_risk = checks.get("high_risk_claim_sweep") if isinstance(checks, dict) else None
    if isinstance(high_risk, dict):
        value = _qa_loop_int_metric(high_risk.get("item_count"))
        if value is None and isinstance(high_risk.get("items"), list):
            value = len(high_risk["items"])
        if value is not None:
            metrics["high_risk_uncited_claim"] = value
    return metrics


def _active_metric_regressions(
    before_quality_eval: dict[str, Any] | None,
    after_quality_eval: dict[str, Any] | None,
    *,
    active_codes: list[str],
) -> list[dict[str, int | str]]:
    before_metrics = _qa_loop_tier2_metric_counts(before_quality_eval)
    after_metrics = _qa_loop_tier2_metric_counts(after_quality_eval)
    regressions: list[dict[str, int | str]] = []
    for code in sorted(dict.fromkeys(str(item) for item in active_codes if str(item).strip())):
        before = before_metrics.get(code)
        after = after_metrics.get(code)
        if before is not None and after is not None and after > before:
            regressions.append({"code": code, "before": before, "after": after, "delta": after - before})
    return regressions


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
    """Return whether a verified citation-repair candidate can stay canonical.

    The QA loop should not spend scarce human/operator cycles merely to accept a
    candidate that has already passed validation/compile and strictly improves
    the active Tier-2 citation metrics.  Keeping such a candidate lets the next
    automatic QA iteration continue from the better manuscript while final
    readiness remains gated by Tier-2 passing.  Pre-existing non-worsened Tier-2
    blockers such as duplicate-support findings may remain for later executable
    handlers, but the candidate must not add new failures, regress active
    metrics, or leave non-human-reviewable citation-support failures.
    """

    if validation_payload.get("ok") is not True:
        return False, "validation_failed"
    if require_compile and (not isinstance(compile_payload, dict) or compile_payload.get("ok") is not True):
        return False, "compile_failed"
    if progress.get("forward_progress") is not True:
        return False, "no_forward_progress"
    if progress.get("new_codes"):
        return False, "new_failure_codes"
    after_statuses = quality_eval_status(after_quality_eval or {})
    if after_statuses.get("tier_0_preconditions") == "fail":
        return False, "tier0_failed"
    if after_statuses.get("tier_1_structural") == "fail":
        return False, "tier1_failed"
    regressions = _active_metric_regressions(
        before_quality_eval,
        after_quality_eval,
        active_codes=[str(code) for code in progress.get("before_failing_codes") or []],
    )
    if regressions:
        return False, "active_tier2_metric_regression"
    non_human_reviewable_residuals = sorted(
        code
        for code in residual_citation_failures
        if code not in {"citation_support_manual_check", "citation_support_weak"}
    )
    if non_human_reviewable_residuals:
        return False, "non_human_reviewable_citation_support_residuals"
    return True, "strict_progress_without_new_failures"
