from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperorchestra.models import InputBundle
from paperorchestra.orchestra_planner import ActionPlanner
from paperorchestra.orchestra_state import OrchestraFacets, OrchestraState
from paperorchestra.orchestrator import inspect_state
from paperorchestra.session import create_session, save_session


class OrchestraStateScenarioTests(unittest.TestCase):
    def test_no_session_and_no_material_guides_to_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = inspect_state(tmp)

        self.assertEqual(state.facets.session, "no_session")
        self.assertEqual(state.readiness.label, "needs_material")
        self.assertIn("provide_material", [action.action_type for action in state.next_actions])

    def test_material_path_with_insufficient_content_records_inventory_and_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            material_dir = Path(tmp) / "synthetic_material"
            material_dir.mkdir()
            (material_dir / "idea.md").write_text("A synthetic method idea.\n", encoding="utf-8")
            state = inspect_state(tmp, material_path=material_dir)

        self.assertEqual(state.facets.material, "inventoried_insufficient")
        self.assertEqual(state.facets.source_digest, "blocked")
        self.assertIn("insufficient_material", state.blocking_reasons)
        self.assertIn("provide_material", [action.action_type for action in state.next_actions])

    def test_current_session_with_paper_full_tex_builds_draft_available_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["idea.md", "experimental_log.md", "template.tex", "conference_guidelines.md"]:
                (root / name).write_text(f"synthetic {name}\n", encoding="utf-8")
            session = create_session(
                tmp,
                InputBundle(
                    idea_path=str(root / "idea.md"),
                    experimental_log_path=str(root / "experimental_log.md"),
                    template_path=str(root / "template.tex"),
                    guidelines_path=str(root / "conference_guidelines.md"),
                ),
            )
            paper = root / ".paper-orchestra" / "runs" / session.session_id / "artifacts" / "paper.full.tex"
            paper.write_text("\\section{Synthetic}\nThis is a synthetic manuscript.\n", encoding="utf-8")
            session.artifacts.paper_full_tex = str(paper)
            save_session(tmp, session)

            state = inspect_state(tmp)

        self.assertEqual(state.facets.session, "draft_available")
        self.assertIsNotNone(state.manuscript_sha256)
        self.assertEqual(len(state.manuscript_sha256 or ""), 64)

    def test_prewriting_notice_required_before_drafting(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(
                material="inventoried_sufficient",
                source_digest="ready",
                claims="validated",
                evidence="supported",
                writing="not_allowed",
            ),
        )
        actions = ActionPlanner().plan(state)
        action_types = [action.action_type for action in actions]

        self.assertIn("show_prewriting_notice", action_types)
        self.assertNotIn("draft", action_types)

    def test_user_interrupt_plans_re_adjudication(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(interaction="interrupted"))
        action_types = [action.action_type for action in ActionPlanner().plan(state)]

        self.assertEqual(action_types[0], "re_adjudicate")

    def test_placeholder_figure_blocks_or_marks_human_finalization_blocker(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(figures="placeholder_only", quality="near_ready"),
        )
        planned = ActionPlanner().plan(state)
        updated = planned[0].state_after if planned and planned[0].state_after is not None else state

        self.assertNotEqual(updated.readiness.label, "ready_for_human_finalization")
        self.assertIn("placeholder_figure_unresolved", updated.blocking_reasons)


if __name__ == "__main__":
    unittest.main()
