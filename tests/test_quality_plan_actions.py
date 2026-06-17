from __future__ import annotations

from paperorchestra.loop_engine.quality.plan_logic import _quality_eval_actions


def _actions_by_code(quality_eval: dict) -> dict[str, dict]:
    return {str(action["code"]): action for action in _quality_eval_actions(quality_eval)}


def test_quality_eval_actions_cover_structural_preconditions_and_compile_blockers() -> None:
    actions = _actions_by_code(
        {
            "tiers": {
                "tier_0_preconditions": {"failing_codes": ["narrative_plan_missing"]},
                "tier_1_structural": {
                    "failing_codes": ["compile_report_missing", "pdf_text_scan_unavailable"],
                    "checks": {"compile_clean": {"source": "compile_report.json"}},
                },
            }
        }
    )

    assert actions["narrative_plan_missing"]["automation"] == "automatic"
    assert actions["narrative_plan_missing"]["target"] == "narrative planning artifacts"
    assert actions["compile_report_missing"]["source"] == "compile_report.json"
    assert actions["compile_report_missing"]["automation"] == "automatic"
    assert actions["pdf_text_scan_unavailable"]["automation"] == "human_needed"
    assert "pdftotext/poppler-utils" in actions["pdf_text_scan_unavailable"]["ralph_instruction"]


def test_quality_eval_actions_classify_citation_support_and_tier3_review_work() -> None:
    actions = _actions_by_code(
        {
            "tiers": {
                "tier_2_claim_safety": {
                    "checks": {
                        "citation_support_critic": {
                            "path": "citation_support_review.json",
                            "failing_codes": [
                                "citation_support_review_stale",
                                "citation_support_unsupported",
                                "citation_support_manual_check",
                            ],
                        }
                    }
                },
                "tier_3_scholarly_quality": {
                    "failing_codes": ["review_score_missing"],
                },
            }
        }
    )

    assert actions["citation_support_review_stale"]["automation"] == "automatic"
    assert actions["citation_support_review_stale"]["source"] == "citation_support_review.json"
    assert actions["citation_support_critic_failed"]["automation"] == "semi_auto"
    assert actions["citation_support_manual_check_requires_author_judgment"]["automation"] == "human_needed"
    assert actions["review_score_missing"]["target"] == "scholarly scorecard"
