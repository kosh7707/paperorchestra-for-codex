from __future__ import annotations

import json
import tempfile
import unittest

from paperorchestra.mcp_server import TOOL_HANDLERS, TOOLS


def _tool_names() -> set[str]:
    return {tool["name"] for tool in TOOLS}


def _decode_text_result(result: dict) -> dict:
    text = result["content"][0]["text"]
    return json.loads(text)


class OrchestratorMcpEntrypointTests(unittest.TestCase):
    def test_mcp_tools_list_contains_high_level_orchestrator_tools(self) -> None:
        names = _tool_names()
        for expected in {"inspect_state", "orchestrate", "continue_project", "answer_human_needed", "export_results"}:
            self.assertIn(expected, names)
            self.assertIn(expected, TOOL_HANDLERS)

    def test_mcp_inspect_state_returns_v1_state_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _decode_text_result(TOOL_HANDLERS["inspect_state"]({"cwd": tmp}))

        self.assertEqual(payload["schema_version"], "orchestra-state/1")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

    def test_mcp_export_results_returns_bounded_plan_when_no_export_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _decode_text_result(TOOL_HANDLERS["export_results"]({"cwd": tmp}))

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")
