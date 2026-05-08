from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paperorchestra.cli import build_parser
from paperorchestra.mcp_server import TOOLS as MCP_TOOLS, TOOL_HANDLERS
from paperorchestra.quality_gate import build_quality_gate_report, write_quality_gate


def _quality_eval(
    *,
    mode: str = "draft",
    provenance_level: str = "live",
    tier0: str = "pass",
    tier1: str = "pass",
    tier2: str = "pass",
    tier3: str = "pass",
    tier0_codes: list[str] | None = None,
    tier1_codes: list[str] | None = None,
    tier2_codes: list[str] | None = None,
    tier3_codes: list[str] | None = None,
    non_reviewable_codes: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "quality-eval/1",
        "session_id": "po-test",
        "mode": mode,
        "manuscript_hash": "sha256:paper",
        "provenance_trust": {"level": provenance_level},
        "non_reviewable": {
            "status": "fail" if non_reviewable_codes else "pass",
            "failing_codes": non_reviewable_codes or [],
        },
        "tiers": {
            "tier_0_preconditions": {"status": tier0, "failing_codes": tier0_codes or []},
            "tier_1_structural": {"status": tier1, "failing_codes": tier1_codes or []},
            "tier_2_claim_safety": {"status": tier2, "failing_codes": tier2_codes or []},
            "tier_3_scholarly_quality": {
                "status": tier3,
                "failing_codes": tier3_codes or [],
                "overall_score": 61.0,
                "axis_scores": {"organization_and_writing": 59.0},
            },
            "tier_4_human_finalization": {
                "status": "never_automated",
                "outstanding_owners": [{"area": "venue_fit", "owner": "human"}],
            },
        },
    }


def _plan(*, actions: list[dict] | None = None, reproducibility_verdict: str = "WARN", fidelity_status: str = "pass") -> dict:
    return {
        "schema_version": "qa-loop-plan/2",
        "session_id": "po-test",
        "verdict": "continue" if actions else "ready_for_human_finalization",
        "verdict_rationale": "test plan",
        "repair_actions": actions or [],
        "audit_snapshots": {
            "reproducibility": {"verdict": reproducibility_verdict},
            "fidelity": {"overall_status": fidelity_status},
        },
        "source_artifacts": {"paper_full_tex": "paper.full.tex"},
        "quality_eval_summary": {"mode": "draft"},
    }


class QualityGateTests(unittest.TestCase):
    def test_claim_safe_profile_blocks_reviewer_warnings_and_reports_all_axes(self) -> None:
        report = build_quality_gate_report(
            _quality_eval(
                mode="claim_safe",
                provenance_level="live",
                tier3="warn",
                tier3_codes=["review_score_below_threshold"],
            ),
            _plan(actions=[{"id": "quality-eval:review-score-low", "code": "review_score_below_threshold"}], reproducibility_verdict="PASS"),
            profile="claim_safe",
            quality_eval_path="quality-eval.json",
            plan_path="qa-loop.plan.json",
        )

        self.assertEqual(report["schema_version"], "quality-gate/1")
        self.assertEqual(report["decision"]["verdict"], "block")
        self.assertTrue(report["decision"]["blocked"])
        self.assertIn("reviewer_acceptability", report["decision"]["blocked_dimensions"])
        self.assertEqual(
            set(report["dimensions"]),
            {
                "structure_latex",
                "citation_claim_safety",
                "story_logic",
                "reviewer_acceptability",
                "reproducibility",
                "human_finalization",
            },
        )
        self.assertEqual(report["dimensions"]["reviewer_acceptability"]["status"], "block")
        self.assertFalse(report["dimensions"]["human_finalization"]["blocking"])

    def test_mock_profile_warns_on_claim_and_review_failures_but_blocks_non_reviewable_structure(self) -> None:
        loose_report = build_quality_gate_report(
            _quality_eval(
                mode="draft",
                provenance_level="mock",
                tier2="fail",
                tier2_codes=["unsupported_comparative_claim"],
                tier3="warn",
                tier3_codes=["section_quality_below_threshold"],
            ),
            _plan(
                actions=[
                    {"id": "quality-eval:citation-support", "code": "unsupported_comparative_claim"},
                    {"id": "quality-eval:section-quality", "code": "section_quality_below_threshold"},
                ],
                reproducibility_verdict="BLOCK",
            ),
            profile="mock",
        )

        self.assertFalse(loose_report["decision"]["blocked"])
        self.assertEqual(loose_report["decision"]["verdict"], "repairable")
        self.assertEqual(loose_report["dimensions"]["citation_claim_safety"]["status"], "warn")
        self.assertEqual(loose_report["dimensions"]["reviewer_acceptability"]["status"], "warn")
        self.assertEqual(loose_report["dimensions"]["reproducibility"]["status"], "warn")

        structural_report = build_quality_gate_report(
            _quality_eval(
                mode="draft",
                provenance_level="mock",
                tier1="fail",
                tier1_codes=["prompt_meta_leakage"],
                non_reviewable_codes=["prompt_meta_leakage"],
            ),
            _plan(reproducibility_verdict="BLOCK"),
            profile="mock",
        )
        self.assertTrue(structural_report["decision"]["blocked"])
        self.assertIn("structure_latex", structural_report["decision"]["blocked_dimensions"])

    def test_write_quality_gate_can_run_auto_refine_and_reevaluate(self) -> None:
        before_eval = _quality_eval(mode="draft", provenance_level="mock", tier3="warn", tier3_codes=["review_score_below_threshold"])
        before_plan = _plan(actions=[{"id": "quality-eval:review-score-low", "code": "review_score_below_threshold"}])
        after_eval = _quality_eval(mode="draft", provenance_level="live")
        after_plan = _plan(reproducibility_verdict="PASS")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_state = SimpleNamespace(notes=[])
            with patch("paperorchestra.quality_gate.write_quality_eval", side_effect=[(root / "quality-eval.json", before_eval), (root / "quality-eval.json", after_eval)]), patch(
                "paperorchestra.quality_gate.write_quality_loop_plan",
                side_effect=[(root / "qa-loop.plan.json", before_plan), (root / "qa-loop.plan.json", after_plan)],
            ), patch("paperorchestra.quality_gate.refine_current_paper", return_value={"accepted": 1}), patch(
                "paperorchestra.quality_gate.load_session", return_value=fake_state
            ), patch("paperorchestra.quality_gate.artifact_path", return_value=root / "quality-gate.report.json"), patch(
                "paperorchestra.quality_gate.save_session"
            ) as save_session:
                path, report = write_quality_gate(root, auto_refine=True, provider=object(), profile="mock")

            self.assertEqual(path, root / "quality-gate.report.json")
            self.assertTrue(report["auto_improvement"]["attempted"])
            self.assertEqual(report["auto_improvement"]["refine_result"]["accepted"], 1)
            self.assertEqual(report["decision"]["verdict"], "pass")
            self.assertTrue(path.exists())
            json.loads(path.read_text(encoding="utf-8"))
            save_session.assert_called()

    def test_cli_and_mcp_expose_quality_gate_surface(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["quality-gate", "--profile", "claim_safe", "--quality-mode", "claim_safe", "--auto-refine"])
        self.assertEqual(args.command, "quality-gate")
        self.assertTrue(args.auto_refine)

        mcp_tool_names = {tool["name"] for tool in MCP_TOOLS}
        self.assertIn("quality_gate", mcp_tool_names)
        self.assertIn("quality_gate", TOOL_HANDLERS)


if __name__ == "__main__":
    unittest.main()
