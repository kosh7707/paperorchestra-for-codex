from __future__ import annotations

from paperorchestra.loop_engine.quality import eval as quality_eval
from paperorchestra.loop_engine.quality import eval_tiers
from paperorchestra.loop_engine.quality.eval_preconditions import (
    PreconditionContext,
    PreconditionTierBuilder,
    build_precondition_tier,
)


def test_quality_eval_facade_exports_tier_helpers() -> None:
    assert quality_eval._strict_issue_codes is eval_tiers._strict_issue_codes
    assert quality_eval._tier is eval_tiers._tier
    assert quality_eval._skipped_tier is eval_tiers._skipped_tier
    assert quality_eval._status_from_failures is eval_tiers._status_from_failures


def test_precondition_tier_blocks_missing_paper_without_counting_planning_as_root_failure() -> None:
    result = build_precondition_tier(
        PreconditionContext(
            paper_full_tex="missing/paper.full.tex",
            paper_exists=False,
            manuscript_hash=None,
            reproducibility={
                "strict_content_gate_issues": [
                    {"kind": "validation_report_stale", "code": "validation_report_stale"},
                    {"kind": "unrelated", "code": "ignored_unrelated_issue"},
                    "ignored malformed issue",
                ]
            },
            planning_status={
                "status": "fail",
                "failing_codes": ["narrative_plan_missing", "claim_map_missing"],
                "artifacts": {"narrative_plan": None, "claim_map": None},
            },
        )
    )

    tier = result.tier
    assert tier["status"] == "fail"
    assert tier["failing_codes"] == [
        "manuscript_hash_missing",
        "paper_full_tex_missing",
        "validation_report_stale",
    ]
    assert "narrative_plan_missing" not in tier["failing_codes"]
    assert tier["checks"]["freshness"] == {
        "status": "fail",
        "stale_against_manuscript_hash": ["validation_report_stale"],
        "planning_artifact_issues": ["narrative_plan_missing", "claim_map_missing"],
    }
    assert tier["checks"]["planning_artifacts"] == {
        "status": "fail",
        "failing_codes": ["narrative_plan_missing", "claim_map_missing"],
        "artifacts": {"narrative_plan": None, "claim_map": None},
    }


def test_precondition_tier_counts_planning_freshness_after_paper_exists() -> None:
    builder = PreconditionTierBuilder()
    result = builder.build(
        PreconditionContext(
            paper_full_tex="paper.full.tex",
            paper_exists=True,
            manuscript_hash="a" * 64,
            reproducibility={"strict_content_gate_issues": []},
            planning_status={
                "status": "fail",
                "failing_codes": ["narrative_plan_stale", "citation_placement_plan_stale"],
                "artifacts": {"narrative_plan": "runtime/narrative-plan.json"},
            },
        )
    )

    assert result.planning_freshness_codes == ["narrative_plan_stale", "citation_placement_plan_stale"]
    assert result.tier["status"] == "fail"
    assert result.tier["failing_codes"] == ["citation_placement_plan_stale", "narrative_plan_stale"]
    assert result.artifact_checks["paper_full_tex"] == {"status": "pass", "path": "paper.full.tex"}
    assert result.artifact_checks["manuscript_hash"] == {"status": "pass", "sha256": "a" * 64}


def test_precondition_tier_passes_with_fresh_artifacts() -> None:
    result = build_precondition_tier(
        PreconditionContext(
            paper_full_tex="paper.full.tex",
            paper_exists=True,
            manuscript_hash="b" * 64,
            reproducibility={"strict_content_gate_issues": []},
            planning_status={"status": "pass", "failing_codes": [], "artifacts": {}},
        )
    )

    assert result.tier["status"] == "pass"
    assert result.tier["failing_codes"] == []
    assert result.tier["checks"]["freshness"]["status"] == "pass"
