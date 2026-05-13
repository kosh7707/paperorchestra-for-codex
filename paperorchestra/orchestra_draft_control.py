from __future__ import annotations

from dataclasses import dataclass, field

from .orchestra_planner import ActionPlanner
from .orchestra_state import NextAction, OrchestraFacets, OrchestraState

HIGH_CRITICAL_CLAIM_TYPES = {"numeric", "comparative", "security", "novelty", "causal"}
HIGH_CRITICAL_GRAPH_ROLES = {"root", "central_support"}
MEDIUM_CRITICAL_CLAIM_TYPES = {"method", "limitation"}


@dataclass(frozen=True)
class ClaimSignal:
    claim_id: str
    claim_type: str
    graph_role: str
    evidence_status: str = "unknown"
    author_desired_strength: str = "unspecified"


@dataclass(frozen=True)
class EvidenceObligationSignal:
    obligation_id: str
    claim_id: str
    status: str
    machine_solvable: bool = True


@dataclass(frozen=True)
class CitationObligationSignal:
    obligation_id: str
    claim_id: str
    status: str
    critical: bool = False


@dataclass
class DraftControlInput:
    base_state: OrchestraState
    claims: list[ClaimSignal] = field(default_factory=list)
    evidence_obligations: list[EvidenceObligationSignal] = field(default_factory=list)
    citation_obligations: list[CitationObligationSignal] = field(default_factory=list)
    evidence_obligation_map_present: bool = True
    prewriting_notice_acknowledged: bool = False
    author_override: str | None = None


@dataclass
class DraftControlDecision:
    status: str
    state: OrchestraState
    actions: list[NextAction]
    reasons: list[str] = field(default_factory=list)
    draft_allowed: bool = False


class DraftControlPolicy:
    def evaluate(self, inputs: DraftControlInput) -> DraftControlDecision:
        state = inputs.base_state.clone()
        state.author_override = inputs.author_override or state.author_override
        reasons: list[str] = []

        if not inputs.claims:
            state.facets.claims = "missing"
            action = NextAction("build_claim_graph", "claim_graph_missing", state_after=state)
            state.next_actions = [action]
            return DraftControlDecision("blocked", state, [action], ["claim_graph_missing"], draft_allowed=False)

        if not inputs.evidence_obligation_map_present:
            state.facets.claims = "candidate"
            state.facets.evidence = "missing"
            action = NextAction("build_evidence_obligations", "evidence_obligations_missing", state_after=state)
            state.next_actions = [action]
            return DraftControlDecision(
                "blocked", state, [action], ["evidence_obligations_missing"], draft_allowed=False
            )

        critical_claim_ids = {claim.claim_id for claim in inputs.claims if self._criticality(claim) == "high"}

        critical_citation_blockers = [
            citation
            for citation in inputs.citation_obligations
            if citation.critical and citation.status in {"unknown_reference", "unsupported"}
        ]
        if critical_citation_blockers:
            state.facets.citations = (
                "unknown_refs"
                if any(citation.status == "unknown_reference" for citation in critical_citation_blockers)
                else "unsupported_critical"
            )
            state.facets.evidence = "research_needed"
            reasons.append(
                "critical_unknown_reference"
                if state.facets.citations == "unknown_refs"
                else "critical_unsupported_reference"
            )
            if state.author_override:
                reasons.append("author_override_cannot_bypass_critical_blocker")
            action = NextAction(
                "start_autoresearch",
                reasons[0],
                requires_omx=True,
                omx_surface="$autoresearch",
                risk="medium",
                evidence_required=True,
                state_after=state,
            )
            state.next_actions = [action]
            return DraftControlDecision("research_needed", state, [action], reasons, draft_allowed=False)

        durable_gap = self._first_obligation(inputs.evidence_obligations, {"durable_research_needed"})
        if durable_gap is not None:
            state.facets.evidence = "durable_research_needed"
            actions = ActionPlanner().plan(state)
            state.next_actions = actions
            return DraftControlDecision("research_needed", state, actions, ["durable_research_needed"], False)

        machine_gap = next(
            (
                obligation
                for obligation in inputs.evidence_obligations
                if obligation.machine_solvable and obligation.status in {"missing", "research_needed"}
            ),
            None,
        )
        if machine_gap is not None:
            state.facets.evidence = "research_needed"
            actions = ActionPlanner().plan(state)
            state.next_actions = actions
            return DraftControlDecision("research_needed", state, actions, ["machine_solvable_evidence_gap"], False)

        high_conflict = any(
            claim.claim_id in critical_claim_ids and claim.evidence_status in {"conflict", "contradicted"}
            for claim in inputs.claims
        ) or any(
            obligation.claim_id in critical_claim_ids and obligation.status in {"conflict", "contradicted"}
            for obligation in inputs.evidence_obligations
        )
        if high_conflict:
            state.facets.claims = "conflict"
            state.facets.interaction = "human_needed"
            actions = ActionPlanner().plan(state)
            state.next_actions = actions
            return DraftControlDecision("human_needed", state, actions, ["high_criticality_claim_conflict"], False)

        low_unsupported = next(
            (
                claim
                for claim in inputs.claims
                if self._criticality(claim) == "low"
                and (
                    claim.evidence_status in {"missing", "unknown"}
                    or any(
                        obligation.claim_id == claim.claim_id
                        and obligation.status in {"missing", "unsupported"}
                        and not obligation.machine_solvable
                        for obligation in inputs.evidence_obligations
                    )
                )
            ),
            None,
        )
        if low_unsupported is not None:
            state.facets.claims = "candidate"
            action = NextAction(
                "auto_weaken_or_delete_claim",
                "low_criticality_unsupported_claim",
                risk="low",
                evidence_required=True,
                state_after=state,
            )
            state.next_actions = [action]
            return DraftControlDecision("blocked", state, [action], ["low_criticality_unsupported_claim"], False)

        state.facets = OrchestraFacets(
            session=state.facets.session,
            material="inventoried_sufficient",
            source_digest="ready",
            claims="validated",
            evidence="supported",
            citations="supported" if inputs.citation_obligations else state.facets.citations,
            figures=state.facets.figures,
            writing="drafting_allowed" if inputs.prewriting_notice_acknowledged else "not_allowed",
            quality=state.facets.quality,
            interaction=state.facets.interaction,
            omx=state.facets.omx,
            artifacts=state.facets.artifacts,
        )
        state.refresh_derived_fields()

        if inputs.prewriting_notice_acknowledged:
            state.next_actions = []
            return DraftControlDecision("draft_allowed", state, [], [], True)

        action = NextAction("show_prewriting_notice", "prewriting_notice_required", state_after=state)
        state.next_actions = [action]
        return DraftControlDecision("blocked", state, [action], ["prewriting_notice_required"], False)

    def _criticality(self, claim: ClaimSignal) -> str:
        if claim.claim_type in HIGH_CRITICAL_CLAIM_TYPES or claim.graph_role in HIGH_CRITICAL_GRAPH_ROLES:
            return "high"
        if claim.claim_type in MEDIUM_CRITICAL_CLAIM_TYPES:
            return "medium"
        return "low"

    def _first_obligation(
        self, obligations: list[EvidenceObligationSignal], statuses: set[str]
    ) -> EvidenceObligationSignal | None:
        return next((obligation for obligation in obligations if obligation.status in statuses), None)
