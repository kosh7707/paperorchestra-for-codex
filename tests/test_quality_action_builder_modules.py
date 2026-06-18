from __future__ import annotations

from paperorchestra.loop_engine.quality import action_builders



def test_quality_eval_actions_still_routes_across_all_tiers() -> None:
    actions = action_builders._quality_eval_actions(
        {
            "tiers": {
                "tier_0_preconditions": {"failing_codes": ["narrative_plan_missing"]},
                "tier_1_structural": {"failing_codes": ["compile_report_missing"], "checks": {"compile_clean": {"source": "compile.json"}}},
                "tier_2_claim_safety": {
                    "checks": {
                        "high_risk_claim_sweep": {"status": "fail"},
                        "planning_satisfaction": {"status": "fail"},
                    }
                },
                "tier_3_scholarly_quality": {"failing_codes": ["review_score_missing"]},
            }
        }
    )

    codes = {str(action["code"]) for action in actions}
    assert {
        "narrative_plan_missing",
        "compile_report_missing",
        "high_risk_uncited_claim",
        "planning_satisfaction_failed",
        "review_score_missing",
    } <= codes
