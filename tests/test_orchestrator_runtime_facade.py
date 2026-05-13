from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestrator import OrchestraOrchestrator, inspect_state
from paperorchestra.orchestra_state import NextAction, OrchestraState


class OrchestratorRuntimeFacadeTests(unittest.TestCase):
    def test_facade_inspect_state_matches_module_function_public_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "idea.md").write_text("synthetic idea\n", encoding="utf-8")
            facade_payload = OrchestraOrchestrator(root).inspect_state(material_path=material).to_public_dict()
            module_payload = inspect_state(root, material_path=material).to_public_dict()

        self.assertEqual(facade_payload, module_payload)

    def test_run_until_blocked_returns_bounded_public_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = OrchestraOrchestrator(tmp).run_until_blocked()
            payload = result.to_public_dict()

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["action_taken"], "none")
        self.assertTrue(payload["private_safe"])
        self.assertEqual(payload["state"]["schema_version"], "orchestra-state/1")
        self.assertIn("scorecard_summary", payload["state"])
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")

    def test_result_public_dict_omits_private_notes_and_author_override_text(self) -> None:
        private = "PRIVATE_AUTHOR_OVERRIDE_SHOULD_NOT_LEAK"
        state = OrchestraState.new(
            cwd="/tmp/example",
            private_notes=["PRIVATE_NOTE_SHOULD_NOT_LEAK"],
            author_override=private,
            next_actions=[NextAction("block", "synthetic")],
        )
        result = OrchestraOrchestrator("/tmp/example")._result_from_state(state)
        rendered = json.dumps(result.to_public_dict(), ensure_ascii=False)

        self.assertNotIn("PRIVATE_NOTE_SHOULD_NOT_LEAK", rendered)
        self.assertNotIn(private, rendered)
        self.assertIn('"author_override": "redacted"', rendered)

    def test_step_with_insufficient_material_plans_provide_material_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "idea.md").write_text("synthetic idea\n", encoding="utf-8")
            result = OrchestraOrchestrator(root).step(material_path=material)
            payload = result.to_public_dict()

        self.assertEqual(payload["execution"], "bounded_plan_only")
        self.assertEqual(payload["action_taken"], "none")
        self.assertEqual(payload["next_actions"][0]["action_type"], "provide_material")
        self.assertNotIn("paper_full_tex", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
