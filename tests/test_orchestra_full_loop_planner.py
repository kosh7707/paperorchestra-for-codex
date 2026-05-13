from __future__ import annotations

import unittest

from paperorchestra.orchestra_consensus import ConsensusPolicy, CriticVerdict
from paperorchestra.orchestra_loop import FullLoopPlanner, LoopFacts
from paperorchestra.orchestra_planner import KNOWN_ACTIONS
from paperorchestra.orchestra_scoring import SCORE_DIMENSIONS, ScholarlyScore, ScoreDimensionAssessment, ScoringBundleBuilder
from paperorchestra.orchestra_state import HardGateStatus, OrchestraFacets, OrchestraState, ScoreSummary


def _complete_score(overall: float = 90.0, readiness_band: str = "near_ready") -> ScholarlyScore:
    return ScholarlyScore(
        overall=overall,
        readiness_band=readiness_band,
        evidence_links=["score.json"],
        dimensions={
            dimension: ScoreDimensionAssessment(
                score=overall,
                confidence="medium",
                rationale=f"{dimension} rationale",
                evidence_links=["score.json"],
            )
            for dimension in SCORE_DIMENSIONS
        },
    )


class OrchestraFullLoopPlannerTests(unittest.TestCase):
    def test_hard_gate_fail_overrides_high_score_in_loop_planner(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="fail", failures=["unsupported_critical_claim"]),
            scores=ScoreSummary(overall=95.0, readiness_band="near_ready"),
        )
        decision = FullLoopPlanner().plan(LoopFacts(state=state))
        self.assertEqual(decision.state.readiness.label, "not_ready")
        self.assertEqual(decision.actions[0].action_type, "start_ralph")

    def test_high_risk_readiness_without_consensus_plans_critic_consensus(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(quality="near_ready"))
        score = _complete_score(82.0, "near_ready")
        decision = FullLoopPlanner().plan(LoopFacts(state=state, score=score, high_risk_readiness=True))
        self.assertEqual(decision.actions[0].action_type, "run_critic_consensus")

    def test_consensus_disagreement_plans_third_adjudication(self) -> None:
        consensus = ConsensusPolicy().evaluate(
            [
                CriticVerdict("A", "near_ready", ["score.json"]),
                CriticVerdict("B", "not_ready", ["score.json"]),
            ]
        )
        decision = FullLoopPlanner().plan(LoopFacts(state=OrchestraState.new(cwd="/tmp/example"), consensus=consensus))
        self.assertEqual(decision.actions[0].action_type, "run_third_critic_adjudication")

    def test_missing_scoring_bundle_plans_build_scoring_bundle(self) -> None:
        decision = FullLoopPlanner().plan(LoopFacts(state=OrchestraState.new(cwd="/tmp/example")))
        self.assertEqual(decision.actions[0].action_type, "build_scoring_bundle")

    def test_compile_and_export_planned_only_after_gates_and_consensus_allow(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="draft_available", quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="pass"),
        )
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "paper.full.tex"},
            compressed_evidence={"summary": "safe"},
        )
        score = _complete_score(90.0, "human_finalization_candidate")
        consensus = ConsensusPolicy().evaluate(
            [CriticVerdict("A", "near_ready", ["score.json"]), CriticVerdict("B", "near_ready", ["score.json"])]
        )
        decision = FullLoopPlanner().plan(LoopFacts(state=state, scoring_bundle=bundle, score=score, consensus=consensus))
        self.assertEqual(decision.actions[0].action_type, "compile_current")


    def test_unresolved_placeholder_figures_route_before_compile(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="draft_available", figures="placeholder_only", quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="pass"),
        )
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "paper.full.tex"},
            compressed_evidence={"summary": "safe"},
        )
        score = _complete_score(90.0, "human_finalization_candidate")
        consensus = ConsensusPolicy().evaluate(
            [CriticVerdict("A", "near_ready", ["score.json"]), CriticVerdict("B", "near_ready", ["score.json"])]
        )
        decision = FullLoopPlanner().plan(LoopFacts(state=state, scoring_bundle=bundle, score=score, consensus=consensus))
        self.assertEqual(decision.actions[0].action_type, "match_supplied_figures")
        self.assertNotEqual(decision.actions[0].action_type, "compile_current")

    def test_compile_requires_explicit_hard_gate_pass(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="draft_available", quality="human_finalization_candidate"),
            hard_gates=HardGateStatus(status="unknown"),
        )
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "paper.full.tex"},
            compressed_evidence={"summary": "safe"},
        )
        score = _complete_score(90.0, "human_finalization_candidate")
        consensus = ConsensusPolicy().evaluate(
            [CriticVerdict("A", "near_ready", ["score.json"]), CriticVerdict("B", "near_ready", ["score.json"])]
        )
        decision = FullLoopPlanner().plan(LoopFacts(state=state, scoring_bundle=bundle, score=score, consensus=consensus))
        self.assertEqual(decision.actions[0].action_type, "block")
        self.assertIn("hard_gates_not_passed", decision.reasons)

    def test_not_ready_consensus_does_not_allow_compile(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(session="draft_available", quality="repairable"),
            hard_gates=HardGateStatus(status="pass"),
        )
        bundle = ScoringBundleBuilder().build(
            phase="final",
            manuscript_sha256="a" * 64,
            required_artifacts={"paper": "paper.full.tex"},
            compressed_evidence={"summary": "safe"},
        )
        score = _complete_score(50.0, "rough_draft")
        consensus = ConsensusPolicy().evaluate(
            [CriticVerdict("A", "not_ready", ["score.json"]), CriticVerdict("B", "not_ready", ["score.json"])]
        )
        decision = FullLoopPlanner().plan(LoopFacts(state=state, scoring_bundle=bundle, score=score, consensus=consensus))
        self.assertEqual(decision.actions[0].action_type, "start_ralph")
        self.assertNotEqual(decision.actions[0].action_type, "compile_current")

    def test_deprecated_omx_autoresearch_action_not_known(self) -> None:
        self.assertNotIn("omx autoresearch", " ".join(KNOWN_ACTIONS))

    def test_overall_only_legacy_score_routes_to_build_scoring_bundle(self) -> None:
        state = OrchestraState.new(cwd="/tmp/example", facets=OrchestraFacets(quality="near_ready"))
        score = ScholarlyScore(overall=90.0, readiness_band="near_ready", evidence_links=["score.json"])
        self.assertFalse(score.valid)
        decision = FullLoopPlanner().plan(LoopFacts(state=state, score=score, high_risk_readiness=True))
        self.assertEqual(decision.actions[0].action_type, "build_scoring_bundle")
