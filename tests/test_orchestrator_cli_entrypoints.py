from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import build_parser, main


@contextlib.contextmanager
def _chdir(path: str):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


class OrchestratorCliEntrypointTests(unittest.TestCase):
    def test_cli_parser_exposes_high_level_orchestrator_commands(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["inspect-state"]).command, "inspect-state")
        self.assertEqual(parser.parse_args(["orchestrate"]).command, "orchestrate")
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
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

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
        self.assertEqual(payload["state"]["next_actions"][0]["action_type"], "inspect_material")
        self.assertNotIn("paper_full_tex", json.dumps(payload))
