from __future__ import annotations

from dataclasses import dataclass, field

from paperorchestra.orchestra.policies import ReadinessPolicy
from paperorchestra.orchestra.state import NextAction, OrchestraState


@dataclass
class ActionPlanEvaluation:
    state: OrchestraState
    objective: str | None = None
    strict_omx: bool = False
    current: OrchestraState = field(init=False)

    def __post_init__(self) -> None:
        self.current = ReadinessPolicy().apply(self.state)

    def plan(self) -> list[NextAction]:
        for actions in (
            self._qa_objective(),
            self._strict_omx_block(),
            self._interrupted(),
            self._research_gap(),
            self._claim_conflict(),
            self._repair_needed(),
            self._figure_block(),
            self._material_intake(),
            self._source_and_claim_builders(),
            self._prewriting_notice(),
            self._compiled_export(),
        ):
            if actions is not None:
                return actions
        return [NextAction("block", self.current.readiness.label, risk="low", state_after=self.current)]

    @property
    def facets(self):
        return self.current.facets

    def _qa_objective(self) -> list[NextAction] | None:
        if self.objective != "qa":
            return None
        return [
            NextAction(
                "start_ultraqa",
                "qa_objective_requested",
                requires_omx=True,
                omx_surface="$ultraqa",
                risk="medium",
                evidence_required=True,
                state_after=self.current,
            )
        ]

    def _strict_omx_block(self) -> list[NextAction] | None:
        if not (self.strict_omx and self.facets.omx == "required_missing"):
            return None
        return [
            NextAction(
                "block",
                "missing_omx_invocation_evidence",
                requires_omx=True,
                risk="medium",
                evidence_required=True,
                state_after=self.current,
            )
        ]

    def _interrupted(self) -> list[NextAction] | None:
        if self.facets.interaction != "interrupted":
            return None
        return [NextAction("re_adjudicate", "user_interrupted", risk="medium", state_after=self.current)]

    def _research_gap(self) -> list[NextAction] | None:
        if self.facets.evidence == "durable_research_needed":
            return [
                NextAction(
                    "start_autoresearch_goal",
                    "durable_research_needed",
                    requires_omx=True,
                    omx_surface="$autoresearch-goal",
                    risk="medium",
                    evidence_required=True,
                    state_after=self.current,
                )
            ]
        if self.facets.evidence == "research_needed":
            return [
                NextAction(
                    "start_autoresearch",
                    "research_needed",
                    requires_omx=True,
                    omx_surface="$autoresearch",
                    risk="medium",
                    evidence_required=True,
                    state_after=self.current,
                )
            ]
        return None

    def _claim_conflict(self) -> list[NextAction] | None:
        if self.facets.claims != "conflict":
            return None
        return [
            NextAction(
                "start_deep_interview",
                "high_risk_claim_conflict",
                requires_omx=True,
                omx_surface="$deep-interview",
                risk="high",
                evidence_required=True,
                state_after=self.current,
            )
        ]

    def _repair_needed(self) -> list[NextAction] | None:
        if self.facets.quality != "repairable":
            return None
        if "high_risk_repair" in self.current.blocking_reasons:
            return [
                NextAction(
                    "start_ralplan",
                    "high_risk_repair",
                    requires_omx=True,
                    omx_surface="$ralplan",
                    risk="high",
                    evidence_required=True,
                    state_after=self.current,
                )
            ]
        return [
            NextAction(
                "start_ralph",
                "repair_needed",
                requires_omx=True,
                omx_surface="$ralph",
                risk="medium",
                evidence_required=True,
                state_after=self.current,
            )
        ]

    def _figure_block(self) -> list[NextAction] | None:
        if self.facets.figures != "placeholder_only":
            return None
        return [NextAction("block", "placeholder_figure_unresolved", risk="medium", state_after=self.current)]

    def _material_intake(self) -> list[NextAction] | None:
        if self.facets.material == "missing" and self.facets.session == "no_session":
            return [NextAction("provide_material", "no_session_or_material", state_after=self.current)]
        if self.facets.material == "inventoried_insufficient":
            return [NextAction("provide_material", "insufficient_material", risk="low", state_after=self.current)]
        if self.facets.material == "inventory_needed":
            return [NextAction("inspect_material", "material_inventory_needed", state_after=self.current)]
        return None

    def _source_and_claim_builders(self) -> list[NextAction] | None:
        if self.facets.material == "inventoried_sufficient" and self.facets.source_digest == "missing":
            return [NextAction("build_source_digest", "source_digest_missing", state_after=self.current)]
        if self.facets.source_digest == "ready" and self.facets.claims == "missing":
            return [NextAction("build_claim_graph", "claim_graph_missing", state_after=self.current)]
        if self.facets.claims == "validated" and self.facets.evidence == "missing":
            return [NextAction("build_evidence_obligations", "evidence_obligations_missing", state_after=self.current)]
        return None

    def _prewriting_notice(self) -> list[NextAction] | None:
        if not (
            self.facets.material == "inventoried_sufficient"
            and self.facets.source_digest == "ready"
            and self.facets.claims == "validated"
            and self.facets.evidence == "supported"
            and self.facets.writing == "not_allowed"
        ):
            return None
        return [NextAction("show_prewriting_notice", "prewriting_notice_required", state_after=self.current)]

    def _compiled_export(self) -> list[NextAction] | None:
        if self.facets.session != "compiled":
            return None
        return [NextAction("export_current", "compiled_artifact_available", state_after=self.current)]


__all__ = ["ActionPlanEvaluation"]
