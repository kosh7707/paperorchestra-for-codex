from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paperorchestra.cli as cli
import paperorchestra.quality_loop as quality_loop
import paperorchestra.ralph_bridge as ralph_bridge
from paperorchestra.providers import MockProvider


class LoopFacadeCompatibilityTests(unittest.TestCase):
    def test_quality_loop_facade_exports_stable_symbols(self) -> None:
        for name in [
            "DEFAULT_MAX_ITERATIONS",
            "QA_LOOP_SUPPORTED_HANDLER_CODES",
            "REVIEW_REFRESH_CODES",
            "append_quality_loop_history",
            "build_quality_eval",
            "build_quality_loop_plan",
            "quality_loop_history_path",
            "write_quality_eval",
            "write_quality_loop_plan",
            "BENCHMARK_CLAIM_RE",
            "HIGH_RISK_CLAIM_RE",
            "LIMITATION_SCOPE_RE",
            "SECURITY_CLAIM_RE",
            "_build_cross_iteration",
            "_citation_actions",
            "_citation_support_check",
            "_citation_support_path",
            "_commands_for_validation_issue",
            "_current_review_records",
            "_dedupe_actions",
            "_fidelity_actions",
            "_failing_codes_from_quality_eval",
            "_figure_review_actions",
            "_file_sha256",
            "_generated_placeholder_figure_actions",
            "_high_risk_claim_sweep",
            "_history_entry_consumes_budget",
            "_human_handoff",
            "_leakage_markers_in_text",
            "_manuscript_prompt_leakage",
            "_mode_actions",
            "_next_ralph_instruction",
            "_numeric_axis_scores",
            "_path_ref",
            "_pdf_text_for_prompt_leakage",
            "_plan_reads",
            "_plan_verdict",
            "_plot_asset_text_paths",
            "_quality_eval_actions",
            "_quality_eval_ready",
            "_quality_eval_summary_for_plan",
            "_read_json_if_exists",
            "_read_quality_history",
            "_review_score_check",
            "_reviewer_independence_check",
            "_resolve_axis_drop_tolerance",
            "_scan_text_file_for_prompt_leakage",
            "_section_quality_check",
            "_sha256_jsonable",
            "_source_material_fidelity_check",
            "_strict_content_actions",
            "_tier_statuses",
            "_validation_actions",
            "_validation_issue_counts",
            "_warning_actions",
        ]:
            self.assertTrue(hasattr(quality_loop, name), name)

    def test_ralph_bridge_facade_exports_stable_symbols(self) -> None:
        for name in [
            "StepResult",
            "build_qa_loop_brief",
            "build_ralph_start_payload",
            "compute_progress_delta",
            "launch_omx_ralph",
            "qa_loop_exit_code",
            "repair_citation_claims",
            "run_qa_loop_step",
            "write_qa_loop_brief",
            "_artifact_sha",
            "_citation_issue_count",
            "_citation_summary",
            "_failing_codes",
            "_non_supported_citation_items",
            "_plan_path",
            "_qa_loop_step_command",
            "_read_json",
            "_repair_prompt",
            "write_quality_eval",
            "write_quality_loop_plan",
        ]:
            self.assertTrue(hasattr(ralph_bridge, name), name)

    def test_ralph_bridge_patch_targets_still_affect_run_step(self) -> None:
        before_eval = {
            "session_id": "po-test",
            "mode": "claim_safe",
            "tiers": {"tier_1_structural": {"status": "fail", "failing_codes": ["missing_prompt_trace"]}},
        }
        plan = {
            "verdict": "human_needed",
            "repair_actions": [
                {"code": "missing_prompt_trace", "automation": "human_needed"},
                {"code": "citation_support_review_missing", "automation": "automatic"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("paperorchestra.ralph_bridge.write_quality_eval", return_value=(root / "quality.json", before_eval)) as eval_mock:
                with patch("paperorchestra.ralph_bridge.write_quality_loop_plan", return_value=(root / "plan.json", plan)) as plan_mock:
                    with patch("paperorchestra.ralph_bridge._citation_summary", return_value={}) as summary_mock:
                        result = ralph_bridge.run_qa_loop_step(root, MockProvider())

        self.assertEqual(result.exit_code, 20)
        self.assertEqual(result.payload["verdict"], "human_needed")
        self.assertTrue(result.payload["terminal_noop"])
        eval_mock.assert_called()
        plan_mock.assert_called()
        summary_mock.assert_called()

    def test_cli_uses_facade_entrypoints(self) -> None:
        self.assertIs(cli.write_quality_eval, quality_loop.write_quality_eval)
        self.assertIs(cli.write_quality_loop_plan, quality_loop.write_quality_loop_plan)
        self.assertIs(cli.run_qa_loop_step, ralph_bridge.run_qa_loop_step)
        self.assertIs(cli.repair_citation_claims, ralph_bridge.repair_citation_claims)
        self.assertIs(cli.build_ralph_start_payload, ralph_bridge.build_ralph_start_payload)


if __name__ == "__main__":
    unittest.main()
