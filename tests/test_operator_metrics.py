from __future__ import annotations

from paperorchestra.feedback.operator_metric_counts import _claim_safe_tier2_metric_counts
from paperorchestra.feedback.operator_metric_delta import _active_tier2_metric_delta


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

    metrics = _claim_safe_tier2_metric_counts(quality_eval)

    assert metrics["citation_support_unsupported"] == 2
    assert metrics["citation_support_weak"] == 3
    assert metrics["citation_support_manual_check"] == 4
    assert metrics["high_risk_uncited_claim"] == 2
    assert metrics["critical_unsupported_citation"] == 5
    assert metrics["citation_bomb_detected"] == 1
    assert metrics["source_obligation_missing"] == 1
    assert metrics["source_obligation_numeric_mismatch"] == 1


def test_claim_safe_tier2_metric_counts_prefers_explicit_counts_and_integer_floats() -> None:
    quality_eval = {
        "tiers": {
            "tier_2_claim_safety": {
                "checks": {
                    "citation_support_critic": {
                        "unsupported_count": 2.0,
                        "weakly_supported_count": True,
                        "canonical_summary": {
                            "unsupported": 99,
                            "weakly_supported": 3,
                        },
                    },
                    "citation_quality_gate": {
                        "counts": {
                            "critical_unsupported_count": 4.0,
                            "critical_need_count": False,
                        }
                    },
                }
            }
        }
    }

    metrics = _claim_safe_tier2_metric_counts(quality_eval)

    assert metrics["citation_support_unsupported"] == 2
    assert metrics["citation_support_weak"] == 3
    assert metrics["critical_unsupported_citation"] == 4
    assert "critical_citation_support_missing" not in metrics


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

    delta = _active_tier2_metric_delta(
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


def test_operator_refinement_constraints_deduplicate_quality_and_integrity_codes() -> None:
    from paperorchestra.feedback.operator_contexts.refinement_constraints import _operator_refinement_constraints

    constraints = _operator_refinement_constraints(
        {"tiers": {"tier_2_claim_safety": {"failing_codes": ["b", "a", "a", ""]}}},
        {"failing_codes": ["c", "b", None]},
    )

    assert constraints["before_failing_codes"] == ["None", "a", "b", "c"]
    assert "forbidden_new_tier2_codes" in constraints
    assert any("Do not introduce" in item for item in constraints["hard_constraints"])


def test_compact_prior_rejected_attempts_keeps_only_bounded_private_safe_fields() -> None:
    from paperorchestra.feedback.operator_contexts.prior_attempts import _compact_prior_rejected_attempts

    attempts = [
        {"gate_passed": True, "gate_reasons": ["ignored"]},
        {"gate_passed": False, "gate_reasons": []},
        {
            "attempt_index": 1,
            "candidate_sha256": "sha1",
            "gate_passed": False,
            "gate_reasons": ["blocked", "blocked", "regressed"],
            "resolved_active_failures": ["old", "old", ""],
            "new_tier2_failures": ["new"],
            "candidate_active_failures": ["candidate"],
            "base_active_failures": ["base"],
            "candidate_text": "must not leak",
            "artifact_path": "/private/path",
            "active_tier2_metric_delta": {
                "improvements": [{"code": "old", "before": 2, "after": 1, "delta": -1}],
                "regressions": [{"code": "", "before": 1, "after": 2, "delta": 1}, {"code": "new", "before": 0, "after": 1, "delta": 1}],
                "base_total": 2,
                "candidate_total": 2,
            },
        },
        {"attempt_index": 2, "candidate_sha256": "sha2", "gate_reasons": ["latest"]},
    ]

    compact = _compact_prior_rejected_attempts(attempts, limit=1)

    assert compact == [
        {
            "attempt_index": 2,
            "candidate_sha256": "sha2",
            "gate_reasons": ["latest"],
            "resolved_active_failures": [],
            "new_tier2_failures": [],
            "candidate_active_failures": [],
            "base_active_failures": [],
            "metric_regressions": [],
            "metric_improvements": [],
            "base_total": None,
            "candidate_total": None,
        }
    ]
