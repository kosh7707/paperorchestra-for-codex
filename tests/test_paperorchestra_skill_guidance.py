from __future__ import annotations

import unittest
from pathlib import Path


class PaperOrchestraSkillGuidanceTests(unittest.TestCase):
    def test_skill_guides_first_use_to_high_level_orchestrator_not_readme_dump(self) -> None:
        text = Path("skills/paperorchestra/SKILL.md").read_text(encoding="utf-8")
        for phrase in ["inspect_state", "orchestrate", "continue_project", "answer_human_needed", "export_results"]:
            self.assertIn(phrase, text)
        self.assertIn("Do not dump README", text)
        self.assertIn("write_evidence", text)
        self.assertIn("evidence bundle", text)

    def test_skill_blocks_insufficient_material_and_preserves_mcp_attachment_distinction(self) -> None:
        text = Path("skills/paperorchestra/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("insufficient material", text)
        self.assertIn("blocks drafting", text)
        self.assertIn("registration", text)
        self.assertIn("active attachment", text)
