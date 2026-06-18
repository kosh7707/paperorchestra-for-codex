from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_metric_counts import _claim_safe_tier2_metric_counts


def _active_tier2_metric_delta(
    base_quality_eval: dict[str, Any] | None,
    candidate_quality_eval: dict[str, Any] | None,
    *,
    base_active_failures: list[str],
) -> dict[str, Any]:
    base_metrics = _claim_safe_tier2_metric_counts(base_quality_eval)
    candidate_metrics = _claim_safe_tier2_metric_counts(candidate_quality_eval)
    comparable = _comparable_active_metrics(base_active_failures, base_metrics, candidate_metrics)
    base_total = sum(item["before"] for item in comparable)
    candidate_total = sum(item["after"] for item in comparable)
    return {
        "base_metrics": {item["code"]: item["before"] for item in comparable},
        "candidate_metrics": {item["code"]: item["after"] for item in comparable},
        "regressions": [item for item in comparable if item["delta"] > 0],
        "improvements": [item for item in comparable if item["delta"] < 0],
        "base_total": base_total if comparable else None,
        "candidate_total": candidate_total if comparable else None,
        "total_improved": bool(comparable) and candidate_total < base_total,
    }


def _comparable_active_metrics(
    active_failures: list[str],
    base_metrics: dict[str, int],
    candidate_metrics: dict[str, int],
) -> list[dict[str, Any]]:
    comparable: list[dict[str, Any]] = []
    for code in (str(code) for code in active_failures):
        before = base_metrics.get(code)
        after = candidate_metrics.get(code)
        if before is None or after is None:
            continue
        comparable.append({"code": code, "before": before, "after": after, "delta": after - before})
    return comparable
