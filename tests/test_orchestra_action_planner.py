from __future__ import annotations

import unittest

from paperorchestra.orchestra_planner import ActionPlanner
from paperorchestra.orchestra_state import OrchestraFacets, OrchestraState


class OrchestraActionPlannerTests(unittest.TestCase):
    def _action_types(self, state: OrchestraState, *, objective: str | None = None) -> list[str]:
        return [action.action_type for action in ActionPlanner().plan(state, objective=objective)]

    def test_machine_solvable_citation_gap_routes_to_autoresearch_not_deep_interview(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(evidence="research_needed"))
        action_types = self._action_types(state)

        self.assertIn("start_autoresearch", action_types)
        self.assertNotIn("start_deep_interview", action_types)

    def test_durable_research_gap_routes_to_autoresearch_goal(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(evidence="durable_research_needed"))
        actions = ActionPlanner().plan(state)

        self.assertEqual(actions[0].action_type, "start_autoresearch_goal")
        self.assertTrue(actions[0].requires_omx)
        self.assertEqual(actions[0].omx_surface, "$autoresearch-goal")
        self.assertTrue(actions[0].evidence_required)

    def test_high_risk_claim_conflict_routes_to_deep_interview(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(claims="conflict"))
        action_types = self._action_types(state)

        self.assertIn("start_deep_interview", action_types)

    def test_high_risk_repair_routes_to_ralplan(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(quality="repairable"),
            blocking_reasons=["high_risk_repair"],
        )
        action_types = self._action_types(state)

        self.assertEqual(action_types[0], "start_ralplan")

    def test_repair_needed_routes_to_ralph(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(quality="repairable"))
        action_types = self._action_types(state)

        self.assertIn("start_ralph", action_types)

    def test_qa_objective_routes_to_ultraqa(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example")
        action_types = self._action_types(state, objective="qa")

        self.assertEqual(action_types[0], "start_ultraqa")

    def test_strict_omx_missing_evidence_blocks_readiness_with_evidence_required_action(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(omx="required_missing"))
        actions = ActionPlanner().plan(state, strict_omx=True)

        self.assertEqual(actions[0].action_type, "block")
        self.assertTrue(actions[0].evidence_required)
        self.assertIn("missing_omx_invocation_evidence", actions[0].reason)


if __name__ == "__main__":
    unittest.main()
