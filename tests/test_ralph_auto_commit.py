from __future__ import annotations

from paperorchestra.loop_engine.ralph.auto_commit import (
    _active_metric_regressions,
    _auto_commit_progressive_citation_candidate,
    _qa_loop_tier2_metric_counts,
)


def _quality_eval(*, unsupported: int = 0, duplicate: int = 0, high_risk: int = 0) -> dict:
    return {
        "tier_status": {
            "tier_0_preconditions": "pass",
            "tier_1_structural": "pass",
            "tier_2_claim_safety": "fail" if unsupported or duplicate or high_risk else "pass",
        },
        "tiers": {
            "tier_2_claim_safety": {
                "checks": {
                    "citation_support_critic": {
                        "unsupported_count": unsupported,
                        "summary": {"unsupported": unsupported},
                    },
                    "citation_quality_gate": {"counts": {"duplicate_reference_count": duplicate}},
                    "high_risk_claim_sweep": {"item_count": high_risk},
                }
            }
        },
    }


def test_tier2_metric_counts_collects_citation_quality_and_high_risk() -> None:
    assert _qa_loop_tier2_metric_counts(_quality_eval(unsupported=2, duplicate=1, high_risk=3)) == {
        "citation_support_unsupported": 2,
        "citation_duplicate_support": 1,
        "high_risk_uncited_claim": 3,
    }


def test_tier2_metric_counts_preserves_auto_commit_metric_scope() -> None:
    quality_eval = _quality_eval()
    quality_eval["tiers"]["tier_2_claim_safety"]["checks"]["citation_quality_gate"]["counts"] = {
        "critical_unsupported_count": 2.0,
        "critical_weak_identity_count": 9,
        "critical_need_count": False,
    }

    assert _qa_loop_tier2_metric_counts(quality_eval) == {
        "citation_support_unsupported": 0,
        "critical_unsupported_citation": 2,
        "high_risk_uncited_claim": 0,
    }


def test_active_metric_regressions_only_reports_active_codes() -> None:
    regressions = _active_metric_regressions(
        _quality_eval(unsupported=1, duplicate=1),
        _quality_eval(unsupported=3, duplicate=5),
        active_codes=["citation_support_unsupported"],
    )

    assert regressions == [{"code": "citation_support_unsupported", "before": 1, "after": 3, "delta": 2}]


def test_auto_commit_allows_strict_progress_with_human_reviewable_residuals() -> None:
    allowed, reason = _auto_commit_progressive_citation_candidate(
        progress={"forward_progress": True, "new_codes": [], "before_failing_codes": ["citation_support_unsupported"]},
        validation_payload={"ok": True},
        compile_payload=None,
        require_compile=False,
        before_quality_eval=_quality_eval(unsupported=2),
        after_quality_eval=_quality_eval(unsupported=1),
        after_codes={"citation_support_weak"},
        residual_citation_failures=["citation_support_weak"],
    )

    assert (allowed, reason) == (True, "strict_progress_without_new_failures")


def test_auto_commit_blocks_metric_regression() -> None:
    allowed, reason = _auto_commit_progressive_citation_candidate(
        progress={"forward_progress": True, "new_codes": [], "before_failing_codes": ["citation_support_unsupported"]},
        validation_payload={"ok": True},
        compile_payload=None,
        require_compile=False,
        before_quality_eval=_quality_eval(unsupported=1),
        after_quality_eval=_quality_eval(unsupported=2),
        after_codes=set(),
        residual_citation_failures=[],
    )

    assert (allowed, reason) == (False, "active_tier2_metric_regression")
