from __future__ import annotations

import json
import unittest

from paperorchestra.orchestra_scorecard import build_scorecard_summary, render_scorecard_summary
from paperorchestra.orchestra_state import HardGateStatus, OrchestraFacets, OrchestraState, ScoreSummary


class OrchestraScorecardSummaryTests(unittest.TestCase):
    def test_unscored_state_returns_unscored_public_summary(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example")
        summary = build_scorecard_summary(state)

        self.assertEqual(summary["status"], "unscored")
        self.assertEqual(summary["readiness_label"], "needs_material")
        self.assertTrue(summary["private_safe"])

    def test_scored_state_lists_weakest_accepted_dimensions(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            scores=ScoreSummary(
                overall=72.0,
                readiness_band="repair_needed",
                dimensions={
                    "claim_validity": 70.0,
                    "source_grounding": 42.0,
                    "citation_integrity": 55.0,
                    "technical_specificity": 61.0,
                },
            ),
        )
        summary = build_scorecard_summary(state)

        self.assertEqual(summary["status"], "scored")
        self.assertEqual(summary["weakest_dimensions"][0], {"dimension": "source_grounding", "score": 42.0})
        self.assertEqual(summary["weakest_dimensions"][1], {"dimension": "citation_integrity", "score": 55.0})

    def test_unknown_dimension_is_omitted_from_public_summary(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            scores=ScoreSummary(
                overall=80.0,
                readiness_band="near_ready",
                dimensions={
                    "claim_validity": 80.0,
                    "PRIVATE_DOMAIN_DIMENSION_SHOULD_NOT_LEAK": 1.0,
                },
            ),
        )
        rendered = json.dumps(build_scorecard_summary(state), ensure_ascii=False)

        self.assertNotIn("PRIVATE_DOMAIN_DIMENSION_SHOULD_NOT_LEAK", rendered)
        self.assertIn("claim_validity", rendered)

    def test_hard_gate_failure_blocks_scorecard_despite_high_score(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="fail", failures=["unsupported_critical_claim"]),
            scores=ScoreSummary(
                overall=98.0,
                readiness_band="human_finalization_candidate",
                dimensions={"claim_validity": 98.0},
            ),
        )
        summary = build_scorecard_summary(state)

        self.assertEqual(summary["status"], "blocked_by_hard_gate")
        self.assertIn("unsupported_critical_claim", summary["blockers"])
        self.assertEqual(summary["readiness_label"], "not_ready")

    def test_public_state_includes_scorecard_summary(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example")
        payload = state.to_public_dict()

        self.assertIn("scorecard_summary", payload)
        self.assertEqual(payload["scorecard_summary"]["status"], "unscored")

    def test_render_scorecard_summary_is_compact_and_public_safe(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            scores=ScoreSummary(
                overall=58.0,
                readiness_band="promising_but_blocked",
                dimensions={
                    "source_grounding": 48.0,
                    "PRIVATE_DOMAIN_DIMENSION_SHOULD_NOT_LEAK": 0.0,
                },
            ),
        )
        text = render_scorecard_summary(build_scorecard_summary(state))

        self.assertIn("Score: 58/100 — promising_but_blocked", text)
        self.assertIn("source_grounding: 48", text)
        self.assertNotIn("PRIVATE_DOMAIN_DIMENSION_SHOULD_NOT_LEAK", text)


if __name__ == "__main__":
    unittest.main()
