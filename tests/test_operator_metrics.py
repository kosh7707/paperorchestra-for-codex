from __future__ import annotations

from paperorchestra.feedback import operator_gates, operator_metrics


def test_operator_gates_facade_reexports_metric_helpers() -> None:
    assert operator_gates._int_metric is operator_metrics._int_metric
    assert operator_gates._claim_safe_tier2_metric_counts is operator_metrics._claim_safe_tier2_metric_counts
    assert operator_gates._active_tier2_metric_delta is operator_metrics._active_tier2_metric_delta


def test_claim_safe_tier2_metric_counts_reads_nested_quality_eval_counts() -> None:
    quality_eval = {
        "tiers": {
            "tier_2_claim_safety": {
                "checks": {
                    "citation_support_critic": {
                        "unsupported_count": 2,
                        "summary": {"weakly_supported": 3, "needs_manual_check": 4},
                    },
                    "high_risk_claim_sweep": {"items": [{"id": "a"}, {"id": "b"}]},
                    "citation_quality_gate": {
                        "counts": {
                            "critical_unsupported_count": 5,
                            "citation_bomb_count": 1,
                        }
                    },
                    "source_obligations": {"unsatisfied": [{"id": "x"}]},
                }
            }
        }
    }

    metrics = operator_metrics._claim_safe_tier2_metric_counts(quality_eval)

    assert metrics["citation_support_unsupported"] == 2
    assert metrics["citation_support_weak"] == 3
    assert metrics["citation_support_manual_check"] == 4
    assert metrics["high_risk_uncited_claim"] == 2
    assert metrics["critical_unsupported_citation"] == 5
    assert metrics["citation_bomb_detected"] == 1
    assert metrics["source_obligation_missing"] == 1
    assert metrics["source_obligation_numeric_mismatch"] == 1


def test_active_tier2_metric_delta_tracks_only_comparable_active_codes() -> None:
    base = {
        "tiers": {
            "tier_2_claim_safety": {
                "checks": {
                    "citation_support_critic": {
                        "unsupported_count": 5,
                        "contradicted_count": 1,
                    }
                }
            }
        }
    }
    candidate = {
        "tiers": {
            "tier_2_claim_safety": {
                "checks": {
                    "citation_support_critic": {
                        "unsupported_count": 3,
                        "contradicted_count": 2,
                    }
                }
            }
        }
    }

    delta = operator_metrics._active_tier2_metric_delta(
        base,
        candidate,
        base_active_failures=[
            "citation_support_unsupported",
            "citation_support_contradicted",
            "untracked_code",
        ],
    )

    assert delta["base_metrics"] == {
        "citation_support_unsupported": 5,
        "citation_support_contradicted": 1,
    }
    assert delta["candidate_metrics"] == {
        "citation_support_unsupported": 3,
        "citation_support_contradicted": 2,
    }
    assert delta["improvements"] == [
        {"code": "citation_support_unsupported", "before": 5, "after": 3, "delta": -2}
    ]
    assert delta["regressions"] == [
        {"code": "citation_support_contradicted", "before": 1, "after": 2, "delta": 1}
    ]
    assert delta["base_total"] == 6
    assert delta["candidate_total"] == 5
    assert delta["total_improved"] is True
