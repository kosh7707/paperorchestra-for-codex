from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_omx_executor import FakeOmxRunner, OmxActionExecutor, OmxCommandResult
from paperorchestra.orchestra_state import NextAction, OrchestraState
from paperorchestra.orchestrator import OrchestraOrchestrator


def _write_material(root: Path, *, durable: bool) -> Path:
    material = root / ("durable_material" if durable else "standard_material")
    material.mkdir()
    if durable:
        idea = "We introduce a new generic evidence workflow for manuscript orchestration. The system is evaluated with synthetic artifacts."
    else:
        idea = "The workflow reduces citation uncertainty before drafting. The system preserves artifact evidence for review."
    (material / "idea.md").write_text(idea, encoding="utf-8")
    (material / "experiment_log.md").write_text(
        "Synthetic experiment notes show reviewable artifact evidence and enough source material.",
        encoding="utf-8",
    )
    return material


def _goal_stdout(slug: str = "po-abcdef123456") -> str:
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


class OrchestratorOmxEntrypointTests(unittest.TestCase):
    def test_execute_omx_once_runs_supported_durable_research_goal_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = _write_material(root, durable=True)
            runner = FakeOmxRunner([OmxCommandResult(return_code=0, stdout=_goal_stdout())])
            result = OrchestraOrchestrator(root).execute_omx_once(
                material_path=material,
                runner=runner,
                slug="po-abcdef123456",
            )
            payload = result.to_public_dict()
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["execution"], "bounded_omx_execution")
        self.assertEqual(payload["action_taken"], "start_autoresearch_goal")
        self.assertEqual(payload["execution_record"]["status"], "executed_omx")
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0]["argv"][:3], ["omx", "autoresearch-goal", "create"])
        self.assertTrue(any(ref.get("kind") == "orchestrator_execution_record" for ref in result.state.evidence_refs))
        self.assertNotEqual(payload["state"]["readiness"]["status"], "ready")
        self.assertNotEqual(payload["state"]["facets"]["writing"], "drafting_allowed")
        self.assertNotIn(str(material), rendered)
        self.assertNotIn("omx ", rendered)
        self.assertNotIn("introduce a new generic", rendered)

    def test_execute_omx_once_standard_autoresearch_returns_handoff_without_runner_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = _write_material(root, durable=False)
            runner = FakeOmxRunner([])
            result = OrchestraOrchestrator(root).execute_omx_once(material_path=material, runner=runner)
            payload = result.to_public_dict()
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["execution"], "bounded_omx_execution")
        self.assertEqual(payload["action_taken"], "start_autoresearch")
        self.assertEqual(payload["execution_record"]["status"], "handoff_required")
        self.assertFalse(payload["execution_record"].get("state_rebuild_required"))
        self.assertFalse(result.execution_record.succeeded)
        self.assertEqual(runner.calls, [])
        self.assertTrue(any(ref.get("kind") == "orchestrator_execution_record" for ref in result.state.evidence_refs))
        self.assertNotEqual(payload["state"]["readiness"]["status"], "ready")
        self.assertEqual(payload["state"]["facets"]["evidence"], "research_needed")
        self.assertNotEqual(payload["state"]["facets"]["writing"], "drafting_allowed")
        self.assertIn("omx_action_handoff", rendered)
        self.assertIn("$autoresearch", rendered)
        self.assertNotIn("omx autoresearch", rendered)
        self.assertNotIn(str(material), rendered)

    def test_execute_omx_once_without_omx_action_returns_non_success_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = FakeOmxRunner([])
            result = OrchestraOrchestrator(tmp).execute_omx_once(runner=runner)
            payload = result.to_public_dict()

        self.assertEqual(payload["execution"], "bounded_omx_execution")
        self.assertEqual(payload["action_taken"], "provide_material")
        self.assertEqual(payload["execution_record"]["status"], "unsupported")
        self.assertFalse(payload["execution_record"].get("state_rebuild_required"))
        self.assertEqual(runner.calls, [])

    def test_execute_omx_once_rejects_executor_state_mutation(self) -> None:
        class MutatingExecutor:
            def execute(self, action: NextAction, state: OrchestraState):
                state.facets.writing = "drafting_allowed"
                return OmxActionExecutor(cwd=Path(state.cwd), runner=FakeOmxRunner([])).execute(action, state)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "must not mutate OrchestraState"):
                OrchestraOrchestrator(tmp).execute_omx_once(executor=MutatingExecutor())


if __name__ == "__main__":
    unittest.main()
