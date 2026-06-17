from __future__ import annotations

from paperorchestra.loop_engine.quality import action_builders
from paperorchestra.loop_engine.quality.action_plan import citation_integrity, citation_quality, citation_support, claim_safety, figure_grounding, preconditions, scholarly, source_material


def test_action_builders_facade_reexports_tier_helpers() -> None:
    assert action_builders._append_tier0_precondition_actions is preconditions._append_tier0_precondition_actions
    assert action_builders._append_tier1_structural_actions is preconditions._append_tier1_structural_actions
    assert action_builders._append_tier2_claim_safety_actions is claim_safety._append_tier2_claim_safety_actions
    assert action_builders._append_citation_support_actions is claim_safety._append_citation_support_actions
    assert claim_safety._append_citation_support_actions is citation_support._append_citation_support_actions
    assert claim_safety._append_citation_integrity_actions is citation_integrity._append_citation_integrity_actions
    assert action_builders._append_citation_integrity_actions is citation_integrity._append_citation_integrity_actions
    assert claim_safety._append_citation_quality_actions is citation_quality._append_citation_quality_actions
    assert claim_safety._append_figure_grounding_actions is figure_grounding._append_figure_grounding_actions
    assert claim_safety._append_source_material_fidelity_actions is source_material._append_source_material_fidelity_actions
    assert claim_safety._append_source_obligation_actions is source_material._append_source_obligation_actions
    assert action_builders._append_tier3_scholarly_actions is scholarly._append_tier3_scholarly_actions


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
