from __future__ import annotations

from .orchestra_policies import ReadinessPolicy
from .orchestra_state import NextAction, OrchestraState

KNOWN_ACTIONS = [
    "provide_material",
    "inspect_material",
    "build_source_digest",
    "build_claim_graph",
    "build_evidence_obligations",
    "show_prewriting_notice",
    "start_autoresearch",
    "start_autoresearch_goal",
    "start_deep_interview",
    "start_ralplan",
    "start_ralph",
    "start_ultraqa",
    "record_trace_summary",
    "run_critic_consensus",
    "run_third_critic_adjudication",
    "re_adjudicate",
    "compile_current",
    "export_results",
    "match_supplied_figures",
    "block",
    "auto_weaken_or_delete_claim",
    "build_scoring_bundle",
]


class ActionPlanner:
    def plan(self, state: OrchestraState, *, objective: str | None = None, strict_omx: bool = False) -> list[NextAction]:
        current = ReadinessPolicy().apply(state)
        facets = current.facets

        if objective == "qa":
            return [
                NextAction(
                    "start_ultraqa",
                    "qa_objective_requested",
                    requires_omx=True,
                    omx_surface="$ultraqa",
                    risk="medium",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if strict_omx and facets.omx == "required_missing":
            return [
                NextAction(
                    "block",
                    "missing_omx_invocation_evidence",
                    requires_omx=True,
                    risk="medium",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if facets.interaction == "interrupted":
            return [NextAction("re_adjudicate", "user_interrupted", risk="medium", state_after=current)]
        # Existing explicit blockers/gaps outrank generic intake defaults. This keeps tests and
        # later rebuilt states from losing a known research/claim/repair obligation merely because
        # the minimal facet snapshot still has default material/session values.
        if facets.evidence == "durable_research_needed":
            return [
                NextAction(
                    "start_autoresearch_goal",
                    "durable_research_needed",
                    requires_omx=True,
                    omx_surface="$autoresearch-goal",
                    risk="medium",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if facets.evidence == "research_needed":
            return [
                NextAction(
                    "start_autoresearch",
                    "research_needed",
                    requires_omx=True,
                    omx_surface="$autoresearch",
                    risk="medium",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if facets.claims == "conflict":
            return [
                NextAction(
                    "start_deep_interview",
                    "high_risk_claim_conflict",
                    requires_omx=True,
                    omx_surface="$deep-interview",
                    risk="high",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if facets.quality == "repairable" and "high_risk_repair" in current.blocking_reasons:
            return [
                NextAction(
                    "start_ralplan",
                    "high_risk_repair",
                    requires_omx=True,
                    omx_surface="$ralplan",
                    risk="high",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if facets.quality == "repairable":
            return [
                NextAction(
                    "start_ralph",
                    "repair_needed",
                    requires_omx=True,
                    omx_surface="$ralph",
                    risk="medium",
                    evidence_required=True,
                    state_after=current,
                )
            ]
        if facets.figures == "placeholder_only":
            return [NextAction("block", "placeholder_figure_unresolved", risk="medium", state_after=current)]
        if facets.material == "missing" and facets.session == "no_session":
            return [NextAction("provide_material", "no_session_or_material", state_after=current)]
        if facets.material == "inventoried_insufficient":
            return [NextAction("provide_material", "insufficient_material", risk="low", state_after=current)]
        if facets.material == "inventory_needed":
            return [NextAction("inspect_material", "material_inventory_needed", state_after=current)]
        if facets.material == "inventoried_sufficient" and facets.source_digest == "missing":
            return [NextAction("build_source_digest", "source_digest_missing", state_after=current)]
        if facets.source_digest == "ready" and facets.claims == "missing":
            return [NextAction("build_claim_graph", "claim_graph_missing", state_after=current)]
        if facets.claims == "validated" and facets.evidence == "missing":
            return [NextAction("build_evidence_obligations", "evidence_obligations_missing", state_after=current)]
        if (
            facets.material == "inventoried_sufficient"
            and facets.source_digest == "ready"
            and facets.claims == "validated"
            and facets.evidence == "supported"
            and facets.writing == "not_allowed"
        ):
            return [NextAction("show_prewriting_notice", "prewriting_notice_required", state_after=current)]
        if facets.session == "compiled":
            return [NextAction("export_results", "compiled_artifact_available", state_after=current)]
        return [NextAction("block", current.readiness.label, risk="low", state_after=current)]
