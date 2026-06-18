from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_metric_counts import _claim_safe_tier2_metric_counts, _int_metric

_qa_loop_int_metric = _int_metric


def _qa_loop_tier2_metric_counts(quality_eval: dict[str, Any] | None) -> dict[str, int]:
    """Return generic Tier-2 issue counts for candidate auto-commit guards."""
    metrics = _claim_safe_tier2_metric_counts(quality_eval)
    return {code: value for code, value in metrics.items() if code in _AUTO_COMMIT_METRIC_CODES}


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


_AUTO_COMMIT_METRIC_CODES = {
    "citation_support_unsupported",
    "citation_support_contradicted",
    "citation_support_weak",
    "citation_support_manual_check",
    "citation_support_metadata_only",
    "citation_support_insufficient_evidence",
    "citation_support_evidence_missing",
    "citation_duplicate_support",
    "citation_bomb_detected",
    "critical_citation_support_missing",
    "critical_unsupported_citation",
    "high_risk_uncited_claim",
}
