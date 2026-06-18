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
    """Return compact quantitative Tier-2 blocker metrics for candidate gating."""
    checks = _tier2_checks(quality_eval)
    metrics: dict[str, int] = {}
    _add_citation_support_metrics(metrics, checks.get("citation_support_critic"))
    _add_high_risk_claim_metrics(metrics, checks.get("high_risk_claim_sweep"))
    _add_citation_quality_metrics(metrics, checks.get("citation_quality_gate"))
    _add_source_obligation_metrics(metrics, checks.get("source_obligations"))
    return metrics


def _tier2_checks(quality_eval: dict[str, Any] | None) -> dict[str, Any]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers, dict) else {}
    checks = tier2.get("checks") if isinstance(tier2, dict) else {}
    return checks if isinstance(checks, dict) else {}


def _add_citation_support_metrics(metrics: dict[str, int], support: Any) -> None:
    if not isinstance(support, dict):
        return
    summary = support.get("canonical_summary") or support.get("summary") or {}
    summary = summary if isinstance(summary, dict) else {}
    for code, count_field, summary_field in _CITATION_SUPPORT_FIELDS:
        value = _int_metric(support.get(count_field))
        if value is None:
            value = _int_metric(summary.get(summary_field))
        if value is not None:
            metrics[code] = value


def _add_high_risk_claim_metrics(metrics: dict[str, int], high_risk: Any) -> None:
    if not isinstance(high_risk, dict):
        return
    value = _int_metric(high_risk.get("item_count"))
    items = high_risk.get("items")
    if value is None and isinstance(items, list):
        value = len(items)
    if value is not None:
        metrics["high_risk_uncited_claim"] = value


def _add_citation_quality_metrics(metrics: dict[str, int], citation_quality: Any) -> None:
    if not isinstance(citation_quality, dict):
        return
    counts = citation_quality.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    for code, field in _CITATION_QUALITY_FIELDS:
        value = _int_metric(counts.get(field))
        if value is not None:
            metrics.setdefault(code, value)


def _add_source_obligation_metrics(metrics: dict[str, int], source_obligations: Any) -> None:
    if not isinstance(source_obligations, dict):
        return
    unsatisfied = source_obligations.get("unsatisfied")
    if isinstance(unsatisfied, list):
        metrics["source_obligation_missing"] = len(unsatisfied)
        metrics["source_obligation_numeric_mismatch"] = len(unsatisfied)


_CITATION_SUPPORT_FIELDS = (
    ("citation_support_unsupported", "unsupported_count", "unsupported"),
    ("citation_support_contradicted", "contradicted_count", "contradicted"),
    ("citation_support_weak", "weakly_supported_count", "weakly_supported"),
    ("citation_support_manual_check", "needs_manual_check_count", "needs_manual_check"),
    ("citation_support_metadata_only", "metadata_only_count", "metadata_only"),
    ("citation_support_insufficient_evidence", "insufficient_evidence_count", "insufficient_evidence"),
    ("citation_support_evidence_missing", "evidence_missing_count", "evidence_missing"),
)

_CITATION_QUALITY_FIELDS = (
    ("critical_unsupported_citation", "critical_unsupported_count"),
    ("critical_citation_support_missing", "critical_need_count"),
    ("critical_weak_reference_identity", "critical_weak_identity_count"),
    ("noncritical_weak_reference_identity", "noncritical_weak_identity_count"),
    ("citation_bomb_detected", "citation_bomb_count"),
    ("citation_duplicate_support", "duplicate_reference_count"),
)
