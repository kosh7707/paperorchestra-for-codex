from __future__ import annotations

from dataclasses import dataclass, field

from .orchestra_consensus import CriticConsensus
from .orchestra_policies import ReadinessPolicy
from .orchestra_scoring import ScholarlyScore, ScoringInputBundle
from .orchestra_state import NextAction, OrchestraState


@dataclass
class LoopFacts:
    state: OrchestraState
    scoring_bundle: ScoringInputBundle | None = None
    score: ScholarlyScore | None = None
    consensus: CriticConsensus | None = None
    high_risk_readiness: bool = False
    compiled: bool = False
    exported: bool = False


@dataclass
class LoopDecision:
    state: OrchestraState
    actions: list[NextAction]
    reasons: list[str] = field(default_factory=list)


class FullLoopPlanner:
    def plan(self, facts: LoopFacts) -> LoopDecision:
        state = ReadinessPolicy().apply(facts.state)
        if state.hard_gates.status == "fail":
            action = NextAction(
                "start_ralph",
                "hard_gate_failure_repair_needed",
                requires_omx=True,
                omx_surface="$ralph",
                risk="medium",
                evidence_required=True,
                state_after=state,
            )
            return LoopDecision(state, [action], list(state.hard_gates.failures))

        if facts.consensus and facts.consensus.status == "needs_adjudication" and facts.consensus.next_action:
            return LoopDecision(state, [facts.consensus.next_action], ["critic_consensus_disagreement"])

        if facts.score is None or not facts.score.valid:
            action = NextAction("build_scoring_bundle", "valid_score_missing", state_after=state)
            return LoopDecision(state, [action], ["valid_score_missing"])

        if facts.high_risk_readiness and facts.consensus is None:
            action = NextAction(
                "run_critic_consensus",
                "high_risk_readiness_requires_consensus",
                requires_omx=True,
                omx_surface="$critic-consensus",
                risk="high",
                evidence_required=True,
                state_after=state,
            )
            return LoopDecision(state, [action], ["critic_consensus_missing"])

        if facts.scoring_bundle is None or not facts.scoring_bundle.complete:
            action = NextAction("build_scoring_bundle", "scoring_bundle_missing_or_incomplete", state_after=state)
            return LoopDecision(state, [action], ["scoring_bundle_missing_or_incomplete"])

        if facts.consensus and facts.consensus.status == "pass":
            allowed_bands = {"near_ready", "human_finalization_candidate", "ready_for_human_finalization"}
            if facts.consensus.readiness_band not in allowed_bands:
                action = NextAction(
                    "start_ralph",
                    "critic_consensus_not_ready",
                    requires_omx=True,
                    omx_surface="$ralph",
                    risk="medium",
                    evidence_required=True,
                    state_after=state,
                )
                return LoopDecision(state, [action], ["critic_consensus_not_ready"])
            if state.facets.figures == "placeholder_only":
                action = NextAction(
                    "match_supplied_figures",
                    "placeholder_figure_unresolved",
                    risk="medium",
                    evidence_required=True,
                    state_after=state,
                )
                return LoopDecision(state, [action], ["placeholder_figure_unresolved"])
            if state.hard_gates.status != "pass":
                action = NextAction("block", "hard_gates_not_passed", risk="medium", state_after=state)
                return LoopDecision(state, [action], ["hard_gates_not_passed"])
            if state.facets.session == "draft_available" and not facts.compiled:
                return LoopDecision(state, [NextAction("compile_current", "ready_to_compile", state_after=state)], [])
            if state.facets.session == "compiled" and not facts.exported:
                return LoopDecision(state, [NextAction("export_results", "ready_to_export", state_after=state)], [])

        action = NextAction("block", state.readiness.label, state_after=state)
        return LoopDecision(state, [action], [state.readiness.label])
