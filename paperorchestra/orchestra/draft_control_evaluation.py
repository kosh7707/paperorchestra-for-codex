from __future__ import annotations

from dataclasses import dataclass, field

from paperorchestra.orchestra.draft_control_criticality import claim_signal_criticality
from paperorchestra.orchestra.draft_control_models import (
    ClaimSignal,
    DraftControlDecision,
    DraftControlInput,
)
from paperorchestra.orchestra.planner import ActionPlanner
from paperorchestra.orchestra.state import NextAction, OrchestraFacets, OrchestraState


@dataclass
class DraftControlEvaluation:
    inputs: DraftControlInput
    state: OrchestraState = field(init=False)
    critical_claim_ids: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.state = self.inputs.base_state.clone()
        self.state.author_override = self.inputs.author_override or self.state.author_override
        self.critical_claim_ids = {
            claim.claim_id for claim in self.inputs.claims if claim_signal_criticality(claim) == "high"
        }

    def run(self) -> DraftControlDecision:
        for decision in (
            self._missing_claim_graph(),
            self._missing_evidence_map(),
            self._critical_citation_blocker(),
            self._durable_research_gap(),
            self._machine_solvable_evidence_gap(),
            self._high_criticality_conflict(),
            self._low_criticality_unsupported_claim(),
        ):
            if decision is not None:
                return decision
        return self._final_draft_decision()

    def _missing_claim_graph(self) -> DraftControlDecision | None:
        if self.inputs.claims:
            return None
        self.state.facets.claims = "missing"
        action = NextAction("build_claim_graph", "claim_graph_missing", state_after=self.state)
        return self._finish("blocked", [action], ["claim_graph_missing"], draft_allowed=False)

    def _missing_evidence_map(self) -> DraftControlDecision | None:
        if self.inputs.evidence_obligation_map_present:
            return None
        self.state.facets.claims = "candidate"
        self.state.facets.evidence = "missing"
        action = NextAction("build_evidence_obligations", "evidence_obligations_missing", state_after=self.state)
        return self._finish("blocked", [action], ["evidence_obligations_missing"], draft_allowed=False)

    def _critical_citation_blocker(self) -> DraftControlDecision | None:
        blockers = [
            citation
            for citation in self.inputs.citation_obligations
            if citation.critical and citation.status in {"unknown_reference", "unsupported"}
        ]
        if not blockers:
            return None

        self.state.facets.citations = (
            "unknown_refs" if any(citation.status == "unknown_reference" for citation in blockers) else "unsupported_critical"
        )
        self.state.facets.evidence = "research_needed"
        reason = (
            "critical_unknown_reference"
            if self.state.facets.citations == "unknown_refs"
            else "critical_unsupported_reference"
        )
        reasons = [reason]
        if self.state.author_override:
            reasons.append("author_override_cannot_bypass_critical_blocker")
        action = NextAction(
            "start_autoresearch",
            reason,
            requires_omx=True,
            omx_surface="$autoresearch",
            risk="medium",
            evidence_required=True,
            state_after=self.state,
        )
        return self._finish("research_needed", [action], reasons, draft_allowed=False)

    def _durable_research_gap(self) -> DraftControlDecision | None:
        if not any(obligation.status == "durable_research_needed" for obligation in self.inputs.evidence_obligations):
            return None
        self.state.facets.evidence = "durable_research_needed"
        return self._planned_research_decision(["durable_research_needed"])

    def _machine_solvable_evidence_gap(self) -> DraftControlDecision | None:
        if not any(
            obligation.machine_solvable and obligation.status in {"missing", "research_needed"}
            for obligation in self.inputs.evidence_obligations
        ):
            return None
        self.state.facets.evidence = "research_needed"
        return self._planned_research_decision(["machine_solvable_evidence_gap"])

    def _high_criticality_conflict(self) -> DraftControlDecision | None:
        if not (self._has_conflicting_critical_claim() or self._has_conflicting_critical_obligation()):
            return None
        self.state.facets.claims = "conflict"
        self.state.facets.interaction = "human_needed"
        actions = ActionPlanner().plan(self.state)
        return self._finish("human_needed", actions, ["high_criticality_claim_conflict"], draft_allowed=False)

    def _low_criticality_unsupported_claim(self) -> DraftControlDecision | None:
        if not any(self._low_criticality_claim_is_unsupported(claim) for claim in self.inputs.claims):
            return None
        self.state.facets.claims = "candidate"
        action = NextAction(
            "auto_weaken_or_delete_claim",
            "low_criticality_unsupported_claim",
            risk="low",
            evidence_required=True,
            state_after=self.state,
        )
        return self._finish("blocked", [action], ["low_criticality_unsupported_claim"], draft_allowed=False)

    def _final_draft_decision(self) -> DraftControlDecision:
        self.state.facets = OrchestraFacets(
            session=self.state.facets.session,
            material="inventoried_sufficient",
            source_digest="ready",
            claims="validated",
            evidence="supported",
            citations="supported" if self.inputs.citation_obligations else self.state.facets.citations,
            figures=self.state.facets.figures,
            writing="drafting_allowed" if self.inputs.prewriting_notice_acknowledged else "not_allowed",
            quality=self.state.facets.quality,
            interaction=self.state.facets.interaction,
            omx=self.state.facets.omx,
            artifacts=self.state.facets.artifacts,
        )
        self.state.refresh_derived_fields()

        if self.inputs.prewriting_notice_acknowledged:
            return self._finish("draft_allowed", [], [], draft_allowed=True)

        action = NextAction("show_prewriting_notice", "prewriting_notice_required", state_after=self.state)
        return self._finish("blocked", [action], ["prewriting_notice_required"], draft_allowed=False)

    def _planned_research_decision(self, reasons: list[str]) -> DraftControlDecision:
        actions = ActionPlanner().plan(self.state)
        return self._finish("research_needed", actions, reasons, draft_allowed=False)

    def _finish(
        self,
        status: str,
        actions: list[NextAction],
        reasons: list[str],
        *,
        draft_allowed: bool,
    ) -> DraftControlDecision:
        self.state.next_actions = actions
        return DraftControlDecision(status, self.state, actions, reasons, draft_allowed)

    def _has_conflicting_critical_claim(self) -> bool:
        return any(
            claim.claim_id in self.critical_claim_ids and claim.evidence_status in {"conflict", "contradicted"}
            for claim in self.inputs.claims
        )

    def _has_conflicting_critical_obligation(self) -> bool:
        return any(
            obligation.claim_id in self.critical_claim_ids and obligation.status in {"conflict", "contradicted"}
            for obligation in self.inputs.evidence_obligations
        )

    def _low_criticality_claim_is_unsupported(self, claim: ClaimSignal) -> bool:
        return claim_signal_criticality(claim) == "low" and (
            claim.evidence_status in {"missing", "unknown"} or self._has_unsupported_human_obligation(claim)
        )

    def _has_unsupported_human_obligation(self, claim: ClaimSignal) -> bool:
        return any(
            obligation.claim_id == claim.claim_id
            and obligation.status in {"missing", "unsupported"}
            and not obligation.machine_solvable
            for obligation in self.inputs.evidence_obligations
        )


__all__ = ["DraftControlEvaluation"]
