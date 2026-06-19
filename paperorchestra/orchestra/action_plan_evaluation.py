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
        return [self._action("block", self.current.readiness.label)]

    @property
    def facets(self):
        return self.current.facets

    def _action(
        self,
        action_type: str,
        reason: str,
        *,
        requires_omx: bool = False,
        omx_surface: str | None = None,
        risk: str = "low",
        evidence_required: bool = False,
    ) -> NextAction:
        return NextAction(
            action_type,
            reason,
            requires_omx=requires_omx,
            omx_surface=omx_surface,
            risk=risk,
            evidence_required=evidence_required,
            state_after=self.current,
        )

    def _omx_action(self, action_type: str, reason: str, *, omx_surface: str | None = None, risk: str = "medium") -> NextAction:
        return self._action(
            action_type,
            reason,
            requires_omx=True,
            omx_surface=omx_surface,
            risk=risk,
            evidence_required=True,
        )

    def _qa_objective(self) -> list[NextAction] | None:
        if self.objective != "qa":
            return None
        return [self._omx_action("start_ultraqa", "qa_objective_requested", omx_surface="$ultraqa")]

    def _strict_omx_block(self) -> list[NextAction] | None:
        if not (self.strict_omx and self.facets.omx == "required_missing"):
            return None
        return [self._omx_action("block", "missing_omx_invocation_evidence")]

    def _interrupted(self) -> list[NextAction] | None:
        if self.facets.interaction != "interrupted":
            return None
        return [self._action("re_adjudicate", "user_interrupted", risk="medium")]

    def _research_gap(self) -> list[NextAction] | None:
        if self.facets.evidence == "durable_research_needed":
            return [self._omx_action("start_autoresearch_goal", "durable_research_needed", omx_surface="$autoresearch-goal")]
        if self.facets.evidence == "research_needed":
            return [self._omx_action("start_autoresearch", "research_needed", omx_surface="$autoresearch")]
        return None

    def _claim_conflict(self) -> list[NextAction] | None:
        if self.facets.claims != "conflict":
            return None
        return [self._omx_action("start_deep_interview", "high_risk_claim_conflict", omx_surface="$deep-interview", risk="high")]

    def _repair_needed(self) -> list[NextAction] | None:
        if self.facets.quality != "repairable":
            return None
        if "high_risk_repair" in self.current.blocking_reasons:
            return [self._omx_action("start_ralplan", "high_risk_repair", omx_surface="$ralplan", risk="high")]
        return [self._omx_action("start_ralph", "repair_needed", omx_surface="$ralph")]

    def _figure_block(self) -> list[NextAction] | None:
        if self.facets.figures != "placeholder_only":
            return None
        return [self._action("block", "placeholder_figure_unresolved", risk="medium")]

    def _material_intake(self) -> list[NextAction] | None:
        if self.facets.material == "missing" and self.facets.session == "no_session":
            return [self._action("provide_material", "no_session_or_material")]
        if self.facets.material == "inventoried_insufficient":
            return [self._action("provide_material", "insufficient_material")]
        if self.facets.material == "inventory_needed":
            return [self._action("inspect_material", "material_inventory_needed")]
        return None

    def _source_and_claim_builders(self) -> list[NextAction] | None:
        if self.facets.material == "inventoried_sufficient" and self.facets.source_digest == "missing":
            return [self._action("build_source_digest", "source_digest_missing")]
        if self.facets.source_digest == "ready" and self.facets.claims == "missing":
            return [self._action("build_claim_graph", "claim_graph_missing")]
        if self.facets.claims == "validated" and self.facets.evidence == "missing":
            return [self._action("build_evidence_obligations", "evidence_obligations_missing")]
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
        return [self._action("show_prewriting_notice", "prewriting_notice_required")]

    def _compiled_export(self) -> list[NextAction] | None:
        if self.facets.session != "compiled":
            return None
        return [self._action("export_current", "compiled_artifact_available")]


__all__ = ["ActionPlanEvaluation"]
