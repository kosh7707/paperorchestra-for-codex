from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paperorchestra.mcp_server import TOOL_HANDLERS, TOOLS, _handle_request
from paperorchestra.models import InputBundle
from paperorchestra.orchestra_omx_executor import FakeOmxRunner, OmxActionExecutor, OmxCommandResult
from paperorchestra.session import artifact_path, create_session, save_session


def _tool_names() -> set[str]:
    return {tool["name"] for tool in TOOLS}


def _decode_text_result(result: dict) -> dict:
    text = result["content"][0]["text"]
    return json.loads(text)


class OrchestratorMcpEntrypointTests(unittest.TestCase):
    def _write_sufficient_material(self, root: Path) -> Path:
        material = root / "material"
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

    def _goal_stdout(self, slug: str = "po-abcdef123456") -> str:
        return json.dumps(
            {
                "ok": True,
                "mission": {
                    "mission_path": f".omx/goals/autoresearch/{slug}/mission.json",
                    "rubric_path": f".omx/goals/autoresearch/{slug}/rubric.md",
                    "ledger_path": f".omx/goals/autoresearch/{slug}/ledger.jsonl",
                },
            }
        )

    def _write_durable_material(self, root: Path) -> Path:
        material = root / "durable_material"
        material.mkdir()
        (material / "idea.md").write_text(
            "We introduce a new generic evidence workflow for manuscript orchestration.",
            encoding="utf-8",
        )
        (material / "experiment_log.md").write_text(
            "Synthetic experiment notes preserve artifact evidence for review.",
            encoding="utf-8",
        )
        return material

    def _write_draft_session(self, root: Path) -> None:
        for name, text in {
            "idea.md": "Synthetic idea.\n",
            "experimental_log.md": "Synthetic experiment log.\n",
            "template.tex": "\\documentclass{article}\\begin{document}\\end{document}\n",
            "guidelines.md": "Synthetic guidelines.\n",
        }.items():
            (root / name).write_text(text, encoding="utf-8")
        figures = root / "figures"
        figures.mkdir()
        state = create_session(
            root,
            InputBundle(
                str(root / "idea.md"),
                str(root / "experimental_log.md"),
                str(root / "template.tex"),
                str(root / "guidelines.md"),
                str(figures),
            ),
            allow_outside_workspace=True,
        )
        paper = artifact_path(root, "paper.full.tex", state.session_id)
        paper.write_text("Synthetic draft. PRIVATE_MCP_DRAFT_TEXT_SHOULD_NOT_LEAK\n", encoding="utf-8")
        state.artifacts.paper_full_tex = str(paper)
        state.current_phase = "draft_complete"
        state.active_artifact = "paper.full.tex"
        save_session(root, state)

    def test_mcp_tools_list_contains_high_level_orchestrator_tools(self) -> None:
        names = _tool_names()
        for expected in {"inspect_state", "orchestrate", "continue_project", "answer_human_needed", "export_results"}:
            self.assertIn(expected, names)
            self.assertIn(expected, TOOL_HANDLERS)

    def test_mcp_orchestrator_evidence_options_are_schema_visible(self) -> None:
        tools = {tool["name"]: tool for tool in TOOLS}
        for tool_name in {"orchestrate", "continue_project"}:
            props = tools[tool_name]["inputSchema"]["properties"]
            self.assertIn("write_evidence", props)
            self.assertEqual(props["write_evidence"]["type"], "boolean")
            self.assertIn("evidence_output", props)
            self.assertEqual(props["evidence_output"]["type"], "string")
        self.assertIn("execute_local", tools["orchestrate"]["inputSchema"]["properties"])
        self.assertEqual(tools["orchestrate"]["inputSchema"]["properties"]["execute_local"]["type"], "boolean")
        self.assertIn("plan_full_loop", tools["orchestrate"]["inputSchema"]["properties"])
        self.assertEqual(tools["orchestrate"]["inputSchema"]["properties"]["plan_full_loop"]["type"], "boolean")
        self.assertIn("execute_omx", tools["orchestrate"]["inputSchema"]["properties"])
        self.assertEqual(tools["orchestrate"]["inputSchema"]["properties"]["execute_omx"]["type"], "boolean")

    def test_mcp_inspect_state_returns_v1_state_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _decode_text_result(TOOL_HANDLERS["inspect_state"]({"cwd": tmp}))

        self.assertEqual(payload["schema_version"], "orchestra-state/1")
        self.assertIn("scorecard_summary", payload)
        self.assertEqual(payload["scorecard_summary"]["status"], "unscored")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

    def test_mcp_export_results_returns_bounded_plan_when_no_export_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _decode_text_result(TOOL_HANDLERS["export_results"]({"cwd": tmp}))

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

    def test_mcp_orchestrate_can_write_public_safe_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "main.tex").write_text("We propose a generic orchestration workflow.\n", encoding="utf-8")
            (material / "references.bib").write_text(
                "@article{example2026,title={Example Reference},author={Ada Example},year={2026}}\n",
                encoding="utf-8",
            )
            payload = _decode_text_result(
                TOOL_HANDLERS["orchestrate"]({"cwd": tmp, "material": str(material), "write_evidence": True})
            )
            output_dir = Path(payload["evidence_bundle"]["output_dir"])
            manifest_exists = Path(payload["evidence_bundle"]["manifest_path"]).exists()
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertIn("evidence_bundle", payload)
        self.assertTrue(manifest_exists)
        self.assertNotIn("execution_record", payload)
        self.assertNotIn("paper_full_tex", json.dumps(payload))
        self.assertNotIn(str(root), rendered)

    def test_mcp_orchestrate_execute_local_returns_one_step_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            payload = _decode_text_result(
                TOOL_HANDLERS["orchestrate"]({"cwd": tmp, "material": str(material), "execute_local": True})
            )
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["execution"], "bounded_local_execution")
        self.assertEqual(payload["action_taken"], "build_claim_graph")
        self.assertEqual(payload["execution_record"]["status"], "executed_local")
        self.assertEqual(payload["state"]["facets"]["claims"], "candidate")
        self.assertEqual(payload["next_actions"][0]["action_type"], "start_autoresearch")
        self.assertEqual(payload["next_actions"][0]["omx_surface"], "$autoresearch")
        self.assertNotIn(str(material), rendered)
        self.assertNotIn("citation uncertainty before drafting", rendered)
        self.assertNotIn("paper_full_tex", rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn("codex ", rendered)

    def test_mcp_orchestrate_execute_local_without_material_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _decode_text_result(TOOL_HANDLERS["orchestrate"]({"cwd": tmp, "execute_local": True}))

        self.assertEqual(payload["execution"], "bounded_local_execution")
        self.assertEqual(payload["action_taken"], "provide_material")
        self.assertEqual(payload["execution_record"]["status"], "unsupported")
        self.assertEqual(payload["execution_record"]["reason"], "material_input_required")

    def test_mcp_orchestrate_plan_full_loop_returns_plan_only_without_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_draft_session(root)
            payload = _decode_text_result(TOOL_HANDLERS["orchestrate"]({"cwd": tmp, "plan_full_loop": True}))
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["execution"], "bounded_full_loop_plan")
        self.assertEqual(payload["action_taken"], "none")
        self.assertNotIn("execution_record", payload)
        self.assertEqual(payload["next_actions"][0]["action_type"], "build_scoring_bundle")
        self.assertNotIn("PRIVATE_MCP_DRAFT_TEXT_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn("omx exec", rendered)

    def test_mcp_orchestrate_execute_local_and_plan_full_loop_conflict_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = _handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "orchestrate",
                        "arguments": {"cwd": tmp, "execute_local": True, "plan_full_loop": True},
                    },
                }
            )

        self.assertIsNotNone(response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("mutually exclusive", response["result"]["content"][0]["text"])

    def test_mcp_orchestrate_execute_omx_conflicts_fail_closed(self) -> None:
        conflict_args = [
            {"execute_local": True, "execute_omx": True},
            {"plan_full_loop": True, "execute_omx": True},
            {"execute_local": True, "plan_full_loop": True, "execute_omx": True},
        ]
        for args in conflict_args:
            with self.subTest(args=args), tempfile.TemporaryDirectory() as tmp:
                response = _handle_request(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "orchestrate", "arguments": {"cwd": tmp, **args}},
                    }
                )
                self.assertIsNotNone(response)
                self.assertTrue(response["result"]["isError"])
                self.assertIn("mutually exclusive", response["result"]["content"][0]["text"])

    def test_mcp_orchestrate_execute_omx_returns_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_durable_material(root)
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout=self._goal_stdout())])
            with mock.patch("paperorchestra.mcp_server._make_omx_executor") as factory:
                factory.side_effect = lambda cwd, **_: OmxActionExecutor(
                    cwd=Path(cwd), runner=runner, slug="po-abcdef123456"
                )
                payload = _decode_text_result(
                    TOOL_HANDLERS["orchestrate"]({"cwd": tmp, "material": str(material), "execute_omx": True})
                )
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["execution"], "bounded_omx_execution")
        self.assertEqual(payload["action_taken"], "start_autoresearch_goal")
        self.assertEqual(payload["execution_record"]["status"], "executed_omx")
        self.assertNotIn("omx ", rendered)
        self.assertNotIn(str(material), rendered)

    def test_mcp_orchestrate_execute_omx_write_evidence_includes_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_durable_material(root)
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout=self._goal_stdout())])
            with mock.patch("paperorchestra.mcp_server._make_omx_executor") as factory:
                factory.side_effect = lambda cwd, **_: OmxActionExecutor(
                    cwd=Path(cwd), runner=runner, slug="po-abcdef123456"
                )
                payload = _decode_text_result(
                    TOOL_HANDLERS["orchestrate"](
                        {"cwd": tmp, "material": str(material), "execute_omx": True, "write_evidence": True}
                    )
                )
            output_dir = Path(payload["evidence_bundle"]["output_dir"])
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))

        self.assertIn("orchestrator_execution_record", rendered)
        self.assertNotIn("argv", rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn(str(material), rendered)

    def test_mcp_orchestrate_execute_local_write_evidence_includes_execution_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._write_sufficient_material(root)
            payload = _decode_text_result(
                TOOL_HANDLERS["orchestrate"](
                    {"cwd": tmp, "material": str(material), "execute_local": True, "write_evidence": True}
                )
            )
            output_dir = Path(payload["evidence_bundle"]["output_dir"])
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))

        self.assertIn("orchestrator_execution_record", rendered)
        self.assertNotIn(str(root), rendered)
        self.assertNotIn("Artifact-first review improves", rendered)

    def test_mcp_continue_project_can_write_public_safe_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _decode_text_result(TOOL_HANDLERS["continue_project"]({"cwd": tmp, "write_evidence": True}))
            manifest_path = Path(payload["evidence_bundle"]["manifest_path"])
            manifest_exists = manifest_path.exists()

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertTrue(manifest_exists)

    def test_mcp_tools_call_reports_outside_evidence_output_as_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir()
            outside = Path(tmp) / "outside"
            response = _handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "orchestrate",
                        "arguments": {"cwd": str(root), "write_evidence": True, "evidence_output": str(outside)},
                    },
                }
            )

        self.assertIsNotNone(response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("ValueError", response["result"]["content"][0]["text"])
