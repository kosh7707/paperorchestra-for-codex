from __future__ import annotations

from paperorchestra.loop_engine.quality.gate import build_quality_gate_report


def _plan() -> dict:
    return {
        "session_id": "session-plan",
        "verdict": "continue",
        "verdict_rationale": "repairs remain",
        "quality_eval_summary": {"status": "fail"},
        "source_artifacts": {"extra": "artifact.json"},
        "audit_snapshots": {
            "reproducibility": {"verdict": "BLOCK"},
            "fidelity": {"overall_status": "fail"},
        },
        "repair_actions": [
            {"id": "repair-structure", "code": "compile_not_clean"},
            {"id": "repair-story", "code": "narrative_plan_missing"},
            {"id": "repair-cite", "code": "citation_support_unsupported"},
            {"id": "repair-review", "code": "section_quality_low"},
            {"id": "ignored", "code": "unrelated"},
        ],
    }


def test_quality_gate_report_builds_claim_safe_dimensions_and_decision() -> None:
    quality_eval = {
        "session_id": "session-eval",
        "mode": "claim_safe",
        "provenance_trust": {"level": "mixed"},
        "non_reviewable": {"status": "fail", "failing_codes": ["artifact_stale"]},
        "tiers": {
            "tier_0_preconditions": {"status": "pass", "failing_codes": []},
            "tier_1_structural": {"status": "fail", "failing_codes": ["compile_not_clean"]},
            "tier_2_claim_safety": {
                "status": "fail",
                "failing_codes": ["narrative_plan_missing", "citation_support_unsupported"],
            },
            "tier_3_scholarly_quality": {
                "status": "warn",
                "failing_codes": ["section_quality_low"],
                "overall_score": 0.41,
                "axis_scores": {"story": 0.3},
                "anti_inflation_triggered": True,
            },
            "tier_4_human_finalization": {"status": "never_automated", "outstanding_owners": ["author"]},
        },
    }

    report = build_quality_gate_report(
        quality_eval,
        _plan(),
        profile="auto",
        quality_eval_path="quality.json",
        plan_path="plan.json",
    )

    assert report["schema_version"] == "quality-gate/1"
    assert report["session_id"] == "session-eval"
    assert report["profile"] == "claim_safe"
    assert report["requested_profile"] == "auto"
    assert report["decision"]["verdict"] == "block"
    assert report["decision"]["blocked"] is True
    assert report["decision"]["blocked_dimensions"] == [
        "structure_latex",
        "citation_claim_safety",
        "story_logic",
        "reviewer_acceptability",
        "reproducibility",
    ]
    assert report["dimensions"]["structure_latex"]["failing_codes"] == ["artifact_stale", "compile_not_clean"]
    assert report["dimensions"]["structure_latex"]["details"]["repair_action_ids"] == ["repair-structure"]
    assert report["dimensions"]["story_logic"]["failing_codes"] == ["narrative_plan_missing"]
    assert report["dimensions"]["story_logic"]["details"]["repair_action_ids"] == ["repair-story"]
    assert report["dimensions"]["reproducibility"]["failing_codes"] == [
        "fidelity_fail",
        "provenance_not_live:mixed",
        "reproducibility_block",
    ]
    assert report["dimensions"]["human_finalization"]["status"] == "human_owned"
    assert report["dimensions"]["human_finalization"]["blocking"] is False
    assert report["source_artifacts"] == {
        "quality_eval": "quality.json",
        "qa_loop_plan": "plan.json",
        "extra": "artifact.json",
    }
    assert "paperorchestra quality-gate --auto-refine --refine-iterations 1" in report["next_commands"]


def test_quality_gate_report_mock_profile_warns_on_claim_reviewer_and_repro_failures() -> None:
    quality_eval = {
        "session_id": "session-eval",
        "mode": "draft",
        "provenance_trust": {"level": "mock"},
        "tiers": {
            "tier_0_preconditions": {"status": "pass", "failing_codes": []},
            "tier_1_structural": {"status": "pass", "failing_codes": []},
            "tier_2_claim_safety": {"status": "fail", "failing_codes": ["citation_support_unsupported"]},
            "tier_3_scholarly_quality": {"status": "fail", "failing_codes": ["section_quality_low"]},
            "tier_4_human_finalization": {"status": "never_automated"},
        },
    }
    plan = {"session_id": "session-plan", "verdict": "continue", "repair_actions": []}

    report = build_quality_gate_report(quality_eval, plan, profile="auto")

    assert report["profile"] == "mock"
    assert report["decision"]["verdict"] == "repairable"
    assert report["decision"]["blocked_dimensions"] == []
    assert report["decision"]["warning_dimensions"] == [
        "citation_claim_safety",
        "reviewer_acceptability",
        "reproducibility",
    ]
    assert report["dimensions"]["citation_claim_safety"]["blocking"] is False
    assert report["dimensions"]["reviewer_acceptability"]["blocking"] is False
    assert report["dimensions"]["reproducibility"]["blocking"] is False


def test_quality_gate_private_helper_aliases_remain_available() -> None:
    from paperorchestra.loop_engine.quality import gate

    quality_eval = {
        "mode": "claim_safe",
        "tiers": {"tier_1_structural": {"status": "fail", "failing_codes": ["compile_not_clean"]}},
    }
    plan = {"repair_actions": [{"id": "repair-1", "code": "compile_not_clean"}]}

    assert gate._normalize_profile("auto", quality_eval) == "claim_safe"
    assert gate._tier_status(quality_eval, "tier_1_structural") == "fail"
    assert gate._tier_codes(quality_eval, "tier_1_structural") == ["compile_not_clean"]
    assert gate._status_for_profile("warn", profile="claim_safe", axis="story_logic") == ("block", True)
    assert gate._repair_action_ids(plan, {"compile_not_clean"}) == ["repair-1"]
    assert gate._dimension(name="Demo", status="pass", blocking=False)["name"] == "Demo"
