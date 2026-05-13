from __future__ import annotations

import unittest

from paperorchestra.orchestra_draft_control import (
    CitationObligationSignal,
    ClaimSignal,
    DraftControlInput,
    DraftControlPolicy,
    EvidenceObligationSignal,
)
from paperorchestra.orchestra_state import OrchestraFacets, OrchestraState


class OrchestraDraftControlTests(unittest.TestCase):
    def _evaluate(
        self,
        *,
        claims: list[ClaimSignal] | None = None,
        evidence: list[EvidenceObligationSignal] | None = None,
        citations: list[CitationObligationSignal] | None = None,
        base_state: OrchestraState | None = None,
        evidence_map_present: bool = True,
        prewriting_notice_acknowledged: bool = False,
        author_override: str | None = None,
    ):
        return DraftControlPolicy().evaluate(
            DraftControlInput(
                base_state=base_state or OrchestraState.new(cwd="/tmp/example"),
                claims=claims or [],
                evidence_obligations=evidence or [],
                citation_obligations=citations or [],
                evidence_obligation_map_present=evidence_map_present,
                prewriting_notice_acknowledged=prewriting_notice_acknowledged,
                author_override=author_override,
            )
        )

    def test_missing_claim_graph_plans_build_claim_graph(self) -> None:
        decision = self._evaluate(claims=[])
        self.assertEqual(decision.status, "blocked")
        self.assertEqual(decision.actions[0].action_type, "build_claim_graph")

    def test_missing_evidence_obligations_plan_build_evidence_obligations(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="method", graph_role="local", evidence_status="unknown")],
            evidence_map_present=False,
        )
        self.assertEqual(decision.actions[0].action_type, "build_evidence_obligations")

    def test_machine_solvable_evidence_gap_routes_to_autoresearch_not_human_needed(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="method", graph_role="local", evidence_status="missing")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="research_needed", machine_solvable=True)],
        )
        action_types = [action.action_type for action in decision.actions]
        self.assertEqual(decision.status, "research_needed")
        self.assertIn("start_autoresearch", action_types)
        self.assertNotIn("start_deep_interview", action_types)

    def test_durable_novelty_gap_routes_to_autoresearch_goal(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="novelty", graph_role="root", evidence_status="missing")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="durable_research_needed", machine_solvable=True)],
        )
        self.assertEqual(decision.status, "research_needed")
        self.assertEqual(decision.actions[0].action_type, "start_autoresearch_goal")

    def test_critical_unknown_reference_blocks_drafting(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="comparative", graph_role="root", evidence_status="supported")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="supported")],
            citations=[CitationObligationSignal("R1", claim_id="C1", status="unknown_reference", critical=True)],
        )
        self.assertFalse(decision.draft_allowed)
        self.assertEqual(decision.status, "research_needed")
        self.assertIn("critical_unknown_reference", decision.reasons)

    def test_high_criticality_conflict_routes_to_human_needed(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="security", graph_role="root", evidence_status="conflict")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="conflict", machine_solvable=False)],
        )
        action_types = [action.action_type for action in decision.actions]
        self.assertEqual(decision.status, "human_needed")
        self.assertIn("start_deep_interview", action_types)

    def test_low_criticality_unsupported_background_claim_auto_weakens_not_human_needed(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="background", graph_role="background", evidence_status="missing")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="missing", machine_solvable=False)],
        )
        action_types = [action.action_type for action in decision.actions]
        self.assertEqual(decision.status, "blocked")
        self.assertIn("auto_weaken_or_delete_claim", action_types)
        self.assertNotIn("start_deep_interview", action_types)

    def test_supported_obligations_require_prewriting_notice_before_drafting(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="method", graph_role="local", evidence_status="supported")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="supported")],
            citations=[CitationObligationSignal("R1", claim_id="C1", status="supported", critical=False)],
        )
        self.assertFalse(decision.draft_allowed)
        self.assertEqual(decision.actions[0].action_type, "show_prewriting_notice")

    def test_acknowledged_prewriting_notice_allows_drafting(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="method", graph_role="local", evidence_status="supported")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="supported")],
            citations=[CitationObligationSignal("R1", claim_id="C1", status="supported", critical=False)],
            prewriting_notice_acknowledged=True,
        )
        self.assertTrue(decision.draft_allowed)
        self.assertEqual(decision.state.facets.writing, "drafting_allowed")

    def test_author_override_cannot_bypass_critical_blocker(self) -> None:
        decision = self._evaluate(
            claims=[ClaimSignal("C1", claim_type="numeric", graph_role="root", evidence_status="supported")],
            evidence=[EvidenceObligationSignal("E1", claim_id="C1", status="supported")],
            citations=[CitationObligationSignal("R1", claim_id="C1", status="unsupported", critical=True)],
            author_override="force this claim as ready",
        )
        self.assertFalse(decision.draft_allowed)
        self.assertIn("author_override_cannot_bypass_critical_blocker", decision.reasons)
        self.assertNotEqual(decision.state.readiness.label, "ready_for_human_finalization")


if __name__ == "__main__":
    unittest.main()
