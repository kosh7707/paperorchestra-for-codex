from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import main as cli_main
from paperorchestra.first_user_guide import FIRST_USER_GUIDE_SCHEMA_VERSION, build_first_user_guide, render_first_user_guide_summary
from paperorchestra.mcp_server import TOOL_HANDLERS, TOOLS


def _tool_names() -> set[str]:
    return {tool["name"] for tool in TOOLS}


def _decode_text_result(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


class FirstUserGuideTests(unittest.TestCase):
    def _write_sufficient_material(self, root: Path) -> Path:
        material = root / "PRIVATE_MATERIAL_SHOULD_NOT_LEAK"
        material.mkdir()
        (material / "idea.md").write_text(
            "PaperOrchestra separates claims from evidence for safer manuscript drafting.\n",
            encoding="utf-8",
        )
        (material / "experiment_log.md").write_text(
            "Experiment notes show a synthetic checklist caught unsafe drafting attempts.\n",
            encoding="utf-8",
        )
        return material

    def test_how_to_use_returns_compact_scorecard_not_readme_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_first_user_guide(tmp, intent="how_to_use")
            rendered = json.dumps(payload, ensure_ascii=False)
            summary = render_first_user_guide_summary(payload)

        self.assertEqual(payload["schema_version"], FIRST_USER_GUIDE_SCHEMA_VERSION)
        self.assertEqual(payload["intent"], "how_to_use")
        self.assertTrue(payload["private_safe_summary"])
        for axis in ["material", "evidence", "citations", "figures", "mcp"]:
            self.assertIn(axis, payload["scorecard"])
        self.assertIn("Next", summary)
        self.assertNotIn("README.md", rendered)
        self.assertNotIn("paperorchestra run", rendered)
        self.assertNotIn("quickstart --scenario", rendered)

    def test_write_now_without_material_refuses_drafting_and_offers_safe_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_first_user_guide(tmp, intent="write_now")

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["refusal"]["refused"])
        self.assertIn("insufficient material", payload["refusal"]["reason"])
        next_action_types = {item["action_type"] for item in payload["next_actions"]}
        self.assertIn("provide_material", next_action_types)
        self.assertIn("start_intake", next_action_types)
        self.assertIn("safe_mock_demo", next_action_types)
        self.assertNotIn("draft", next_action_types)

    def test_material_path_is_redacted_but_affects_material_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            payload = build_first_user_guide(root, intent="start", material=material)
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["scorecard"]["material"], "ok")
        self.assertIn("redacted-material-root:", rendered)
        self.assertNotIn(str(material), rendered)
        self.assertNotIn("PRIVATE_MATERIAL_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("synthetic checklist", rendered)

    def test_setup_intent_mentions_registration_attachment_distinction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_first_user_guide(tmp, intent="setup", mcp_attached=False)
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["intent"], "setup")
        self.assertEqual(payload["scorecard"]["mcp"], "registered_only")
        self.assertIn("registration", rendered)
        self.assertIn("active attachment", rendered)
        self.assertIn("restart", rendered)

    def test_mcp_registered_only_uses_cli_fallback_surfaces_for_ready_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            payload = build_first_user_guide(root, intent="start", material=material, mcp_attached="no")

        self.assertEqual(payload["status"], "mcp_fallback")
        self.assertFalse(any(action["surface"] == "mcp" for action in payload["next_actions"]))
        self.assertTrue(any(action["surface"] == "cli" for action in payload["next_actions"]))

    def test_mcp_registered_only_write_now_refusal_has_no_mcp_only_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_first_user_guide(tmp, intent="write_now", mcp_attached="no")

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(payload["refusal"]["refused"])
        self.assertFalse(any(action["surface"] == "mcp" for action in payload["next_actions"]))

    def test_cli_first_use_json_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["first-use", "--intent", "how_to_use", "--json"])
            json_payload = json.loads(stdout.getvalue())
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                summary_exit_code = cli_main(["first-use", "--intent", "write_now"])
            summary = stdout.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary_exit_code, 0)
        self.assertEqual(json_payload["schema_version"], FIRST_USER_GUIDE_SCHEMA_VERSION)
        self.assertIn("Scorecard", summary)
        self.assertIn("Refusal", summary)
        self.assertNotIn("paperorchestra run", summary)

    def test_mcp_first_use_guide_tool_is_registered_and_public_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            payload = _decode_text_result(
                TOOL_HANDLERS["first_use_guide"]({"cwd": str(root), "intent": "start", "material": str(material)})
            )
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertIn("first_use_guide", _tool_names())
        self.assertIn("first_use_guide", TOOL_HANDLERS)
        self.assertEqual(payload["schema_version"], FIRST_USER_GUIDE_SCHEMA_VERSION)
        self.assertTrue(payload["private_safe_summary"])
        self.assertNotIn(str(material), rendered)
        self.assertNotIn("PRIVATE_MATERIAL_SHOULD_NOT_LEAK", rendered)
