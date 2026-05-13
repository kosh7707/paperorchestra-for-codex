from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import _orchestrator_summary_lines, build_parser, main


@contextlib.contextmanager
def _chdir(path: str):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


class OrchestratorCliEntrypointTests(unittest.TestCase):
    def _write_sufficient_material(self, root: Path) -> Path:
        material = root / "synthetic_material"
        material.mkdir()
        (material / "idea.md").write_text(
            "PaperOrchestra improves manuscript safety by separating claims from evidence. "
            "The workflow reduces citation uncertainty before drafting.",
            encoding="utf-8",
        )
        (material / "experiment_log.md").write_text(
            "Experiment results show 12 checklist violations were caught before drafting. "
            "Artifact-first review improves reviewability.",
            encoding="utf-8",
        )
        return material

    def test_cli_parser_exposes_high_level_orchestrator_commands(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["inspect-state"]).command, "inspect-state")
        self.assertEqual(parser.parse_args(["orchestrate"]).command, "orchestrate")
        self.assertTrue(parser.parse_args(["orchestrate", "--execute-local"]).execute_local)
        self.assertEqual(parser.parse_args(["continue-project"]).command, "continue-project")
        self.assertEqual(
            parser.parse_args(["answer-human-needed", "--answer", "Use the supported weaker claim."]).command,
            "answer-human-needed",
        )

    def test_inspect_state_json_returns_orchestra_state_and_next_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["inspect-state", "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], "orchestra-state/1")
        self.assertIn("next_actions", payload)
        self.assertIn("scorecard_summary", payload)
        self.assertEqual(payload["scorecard_summary"]["status"], "unscored")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

    def test_inspect_state_human_summary_includes_scorecard_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["inspect-state"])
            text = stdout.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Score: unscored", text)
        self.assertIn("Readiness:", text)
        self.assertIn("Next action:", text)

    def test_orchestrate_json_returns_bounded_action_plan_not_live_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            material = Path(tmp) / "synthetic_material"
            material.mkdir()
            (material / "idea.md").write_text("synthetic idea\n", encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["orchestrate", "--material", str(material), "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["state"]["facets"]["material"], "inventoried_insufficient")
        self.assertEqual(payload["state"]["next_actions"][0]["action_type"], "provide_material")
        self.assertEqual(payload["state"]["next_actions"][0]["reason"], "insufficient_material")
        self.assertNotIn("execution_record", payload)
        self.assertNotIn("paper_full_tex", json.dumps(payload))

    def test_orchestrate_execute_local_json_returns_one_step_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["orchestrate", "--material", str(material), "--execute-local", "--json"])
            payload = json.loads(stdout.getvalue())
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["execution"], "bounded_local_execution")
        self.assertEqual(payload["execution_record"]["status"], "executed_local")
        self.assertEqual(payload["action_taken"], "build_claim_graph")
        self.assertNotIn(str(material), rendered)
        self.assertNotIn("citation uncertainty before drafting", rendered)
        self.assertNotIn("paper_full_tex", rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn("codex ", rendered)

    def test_orchestrate_execute_local_without_material_is_deterministic_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["orchestrate", "--execute-local", "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["execution"], "bounded_local_execution")
        self.assertEqual(payload["action_taken"], "provide_material")
        self.assertEqual(payload["execution_record"]["status"], "unsupported")
        self.assertEqual(payload["execution_record"]["reason"], "material_input_required")

    def test_orchestrate_execute_local_write_evidence_includes_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    ["orchestrate", "--material", str(material), "--execute-local", "--write-evidence", "--json"]
                )
            payload = json.loads(stdout.getvalue())
            output_dir = Path(payload["evidence_bundle"]["output_dir"])
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))

        self.assertEqual(exit_code, 0)
        self.assertIn("orchestrator_execution_record", rendered)
        self.assertNotIn(str(root), rendered)
        self.assertNotIn("Artifact-first review improves", rendered)

    def test_orchestrate_execute_local_human_summary_shows_execution_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["orchestrate", "--material", str(material), "--execute-local"])
            text = stdout.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Execution: bounded_local_execution", text)
        self.assertIn("Action taken: build_claim_graph", text)
        self.assertIn("Execution status: executed_local", text)
        self.assertIn("Adapter: local", text)
        self.assertNotIn(str(material), text)
        self.assertNotIn("citation uncertainty before drafting", text)
        self.assertNotIn("omx ", text)
        self.assertNotIn("codex ", text)

    def test_orchestrate_execute_local_without_material_human_summary_shows_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["orchestrate", "--execute-local"])
            text = stdout.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Execution: bounded_local_execution", text)
        self.assertIn("Action taken: provide_material", text)
        self.assertIn("Execution status: unsupported", text)
        self.assertIn("Reason: material_input_required", text)

    def test_orchestrator_summary_omits_unknown_private_dimension_label(self) -> None:
        lines = _orchestrator_summary_lines(
            {
                "readiness": {"label": "not_ready"},
                "next_actions": [{"action_type": "build_scoring_bundle"}],
                "scorecard_summary": {
                    "status": "scored",
                    "overall": 58.0,
                    "readiness_band": "repair_needed",
                    "weakest_dimensions": [{"dimension": "source_grounding", "score": 48.0}],
                    "blockers": ["unknown_score_dimension:<redacted>"],
                },
            }
        )
        text = "\n".join(lines)

        self.assertIn("Score: 58/100", text)
        self.assertIn("source_grounding: 48", text)
        self.assertNotIn("PRIVATE_DOMAIN_DIMENSION_SHOULD_NOT_LEAK", text)

    def test_continue_project_write_evidence_json_writes_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["continue-project", "--write-evidence", "--json"])
            payload = json.loads(stdout.getvalue())
            manifest_exists = Path(payload["evidence_bundle"]["manifest_path"]).exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertIn("state", payload)
        self.assertTrue(manifest_exists)
