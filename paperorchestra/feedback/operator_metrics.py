from __future__ import annotations

from typing import Any


def _int_metric(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _claim_safe_tier2_metric_counts(quality_eval: dict[str, Any] | None) -> dict[str, int]:
    """Return compact quantitative Tier-2 blocker metrics for candidate gating.

    Failing-code set comparisons are too coarse for supervised candidates: a
    candidate can resolve one code while making another still-active code worse.
    These metrics are intentionally generic and derived only from quality-eval
    checks, so they apply to any paper domain.
    """
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers, dict) else {}
    checks = tier2.get("checks") if isinstance(tier2, dict) else {}
    metrics: dict[str, int] = {}

    support = checks.get("citation_support_critic") if isinstance(checks, dict) else None
    if isinstance(support, dict):
        support_count_fields = {
            "citation_support_unsupported": "unsupported_count",
            "citation_support_contradicted": "contradicted_count",
            "citation_support_weak": "weakly_supported_count",
            "citation_support_manual_check": "needs_manual_check_count",
            "citation_support_metadata_only": "metadata_only_count",
            "citation_support_insufficient_evidence": "insufficient_evidence_count",
            "citation_support_evidence_missing": "evidence_missing_count",
        }
        summary = support.get("canonical_summary") or support.get("summary") or {}
        summary_fields = {
            "citation_support_unsupported": "unsupported",
            "citation_support_contradicted": "contradicted",
            "citation_support_weak": "weakly_supported",
            "citation_support_manual_check": "needs_manual_check",
            "citation_support_metadata_only": "metadata_only",
            "citation_support_insufficient_evidence": "insufficient_evidence",
            "citation_support_evidence_missing": "evidence_missing",
        }
        for code, field in support_count_fields.items():
            value = _int_metric(support.get(field))
            if value is None and isinstance(summary, dict):
                value = _int_metric(summary.get(summary_fields[code]))
            if value is not None:
                metrics[code] = value

    high_risk = checks.get("high_risk_claim_sweep") if isinstance(checks, dict) else None
    if isinstance(high_risk, dict):
        value = _int_metric(high_risk.get("item_count"))
        if value is None and isinstance(high_risk.get("items"), list):
            value = len(high_risk["items"])
        if value is not None:
            metrics["high_risk_uncited_claim"] = value

    citation_quality = checks.get("citation_quality_gate") if isinstance(checks, dict) else None
    if isinstance(citation_quality, dict):
        counts = citation_quality.get("counts") if isinstance(citation_quality.get("counts"), dict) else {}
        quality_fields = {
            "critical_unsupported_citation": "critical_unsupported_count",
            "critical_citation_support_missing": "critical_need_count",
            "critical_weak_reference_identity": "critical_weak_identity_count",
            "noncritical_weak_reference_identity": "noncritical_weak_identity_count",
            "citation_bomb_detected": "citation_bomb_count",
            "citation_duplicate_support": "duplicate_reference_count",
        }
        for code, field in quality_fields.items():
            value = _int_metric(counts.get(field))
            if value is not None:
                metrics.setdefault(code, value)

    source_obligations = checks.get("source_obligations") if isinstance(checks, dict) else None
    if isinstance(source_obligations, dict):
        unsatisfied = source_obligations.get("unsatisfied")
        if isinstance(unsatisfied, list):
            metrics["source_obligation_missing"] = len(unsatisfied)
            metrics["source_obligation_numeric_mismatch"] = len(unsatisfied)
    return metrics


def _active_tier2_metric_delta(
    base_quality_eval: dict[str, Any] | None,
    candidate_quality_eval: dict[str, Any] | None,
    *,
    base_active_failures: list[str],
) -> dict[str, Any]:
    base_metrics = _claim_safe_tier2_metric_counts(base_quality_eval)
    candidate_metrics = _claim_safe_tier2_metric_counts(candidate_quality_eval)
    active = [str(code) for code in base_active_failures]
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    base_total = 0
    candidate_total = 0
    comparable_codes: list[str] = []
    for code in active:
        before = base_metrics.get(code)
        after = candidate_metrics.get(code)
        if before is None or after is None:
            continue
        comparable_codes.append(code)
        base_total += before
        candidate_total += after
        record = {"code": code, "before": before, "after": after, "delta": after - before}
        if after > before:
            regressions.append(record)
        elif after < before:
            improvements.append(record)
    return {
        "base_metrics": {code: base_metrics[code] for code in comparable_codes if code in base_metrics},
        "candidate_metrics": {code: candidate_metrics[code] for code in comparable_codes if code in candidate_metrics},
        "regressions": regressions,
        "improvements": improvements,
        "base_total": base_total if comparable_codes else None,
        "candidate_total": candidate_total if comparable_codes else None,
        "total_improved": bool(comparable_codes) and candidate_total < base_total,
    }
