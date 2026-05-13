from __future__ import annotations

import unittest
from pathlib import Path


class PaperOrchestraSkillGuidanceTests(unittest.TestCase):
    def _readme(self) -> str:
        return Path("README.md").read_text(encoding="utf-8")

    def _environment(self) -> str:
        return Path("ENVIRONMENT.md").read_text(encoding="utf-8")

    def _skill(self) -> str:
        return Path("skills/paperorchestra/SKILL.md").read_text(encoding="utf-8")

    def test_skill_guides_first_use_to_high_level_orchestrator_not_readme_dump(self) -> None:
        text = self._skill()
        for phrase in ["inspect_state", "orchestrate", "continue_project", "answer_human_needed", "export_results"]:
            self.assertIn(phrase, text)
        self.assertIn("Do not dump README", text)
        self.assertIn("write_evidence", text)
        self.assertIn("evidence bundle", text)

    def test_skill_blocks_insufficient_material_and_preserves_mcp_attachment_distinction(self) -> None:
        text = self._skill()
        self.assertIn("insufficient material", text)
        self.assertIn("blocks drafting", text)
        self.assertIn("registration", text)
        self.assertIn("active attachment", text)

    def test_skill_documents_execute_local_as_one_step_not_full_pipeline(self) -> None:
        text = self._skill()
        self.assertIn("execute_local", text)
        self.assertIn("one deterministic local step", text)
        self.assertIn("not a full pipeline", text)
        self.assertIn("Execution status", text)
        self.assertIn("next action", text)

    def test_skill_routes_machine_solvable_search_to_autoresearch_not_user_homework(self) -> None:
        text = self._skill()
        self.assertIn("machine-solvable citation/search", text)
        self.assertIn("start_autoresearch", text)
        self.assertIn("$autoresearch", text)
        self.assertIn("do not ask the user", text)

    def test_readme_documents_execute_local_no_live_boundary_and_next_action(self) -> None:
        text = self._readme()
        self.assertIn("paperorchestra orchestrate --material ./my-material --execute-local --write-evidence --json", text)
        self.assertIn("execute_local", text)
        self.assertIn("one deterministic local step", text)
        self.assertIn("not a full paper run", text)
        self.assertIn("No live model/search, OMX, compile/export, or drafting", text)
        self.assertIn("start_autoresearch", text)
        self.assertIn("material_input_required", text)

    def test_readme_and_skill_say_evidence_bundles_are_not_readiness_passes(self) -> None:
        combined = self._readme() + "\n" + self._skill()
        self.assertIn("diagnostic artifact", combined)
        self.assertIn("not a readiness pass", combined)

    def test_environment_mentions_no_live_local_step_check(self) -> None:
        text = self._environment()
        self.assertIn("no-live local-step check", text)
        self.assertIn("--execute-local", text)
        self.assertIn("execute_local", text)
