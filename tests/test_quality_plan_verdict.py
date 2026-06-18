from __future__ import annotations

from paperorchestra.loop_engine.quality.plan_readiness import _quality_eval_ready
from paperorchestra.loop_engine.quality.plan_verdict import _plan_verdict


def _quality_eval(*, status: str = "pass", provenance: str = "live", failing_codes: list[str] | None = None) -> dict:
    codes = failing_codes or []
    return {
        "tiers": {
            "tier_0_preconditions": {"status": status, "failing_codes": codes if status != "pass" else []},
            "tier_1_structural": {"status": "pass", "failing_codes": []},
            "tier_2_claim_safety": {"status": "pass", "failing_codes": []},
            "tier_3_scholarly_quality": {"status": "pass", "failing_codes": []},
        },
        "provenance_trust": {"level": provenance, "mixed_acceptance": {"status": "pass"}},
        "cross_iteration": {"budget": {"remaining": 1, "current_attempt_consumes_budget": True}, "regression": {}},
    }


def test_quality_eval_ready_accepts_live_or_approved_mixed_provenance() -> None:
    assert _quality_eval_ready(_quality_eval(), accept_mixed_provenance=False)
    assert not _quality_eval_ready(_quality_eval(provenance="mixed"), accept_mixed_provenance=False)
    assert _quality_eval_ready(_quality_eval(provenance="mixed"), accept_mixed_provenance=True)


def test_plan_verdict_prioritizes_budget_exhaustion_over_action_routing() -> None:
    quality_eval = _quality_eval(status="fail", failing_codes=["validation_report_missing"])
    quality_eval["cross_iteration"]["budget"]["remaining"] = 0

    verdict, rationale = _plan_verdict(
        quality_eval,
        [{"code": "validation_report_missing", "automation": "automatic"}],
        accept_mixed_provenance=False,
    )

    assert verdict == "failed"
    assert "budget exhausted" in rationale


def test_plan_verdict_routes_supported_actions_to_continue() -> None:
    verdict, rationale = _plan_verdict(
        _quality_eval(),
        [{"code": "validation_report_missing", "automation": "automatic"}],
        accept_mixed_provenance=False,
    )

    assert verdict == "continue"
    assert "repair actions remain" in rationale


def test_plan_verdict_marks_ready_when_tiers_pass_and_no_actions_remain() -> None:
    verdict, rationale = _plan_verdict(_quality_eval(), [], accept_mixed_provenance=False)

    assert verdict == "ready_for_human_finalization"
    assert "Tier 0-3 passed" in rationale


def test_plan_verdict_stops_for_hard_human_needed_actions() -> None:
    verdict, rationale = _plan_verdict(
        _quality_eval(),
        [{"code": "mock_provider", "automation": "human_needed"}],
        accept_mixed_provenance=False,
    )

    assert verdict == "human_needed"
    assert "hard human-needed" in rationale
