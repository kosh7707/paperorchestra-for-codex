from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from paperorchestra.orchestra.state_models import ReadinessSummary


@dataclass(frozen=True)
class ReadinessRule:
    predicate: Callable[[Any], bool]
    label: str
    status: str
    rationale: str

    def summary_if_matches(self, state: Any) -> ReadinessSummary | None:
        if not self.predicate(state):
            return None
        return ReadinessSummary(self.label, self.status, self.rationale)


def derive_readiness(state: Any) -> ReadinessSummary:
    for rule in READINESS_RULES:
        summary = rule.summary_if_matches(state)
        if summary is not None:
            return summary
    return ReadinessSummary("not_ready", "blocked", "State is not ready.")


def _hard_gate_failed(state: Any) -> bool:
    return state.hard_gates.status == "fail"


def _author_override_conflicts(state: Any) -> bool:
    facets = state.facets
    return bool(state.author_override and (facets.claims == "conflict" or facets.evidence in {"unresolved", "blocked"}))


def _strict_omx_missing(state: Any) -> bool:
    return state.facets.omx == "required_missing"


def _figure_gate_blocks_final_readiness(state: Any) -> bool:
    facets = state.facets
    return facets.figures in {"placeholder_only", "inventory_needed", "blocked"} and facets.quality in {
        "near_ready",
        "human_finalization_candidate",
    }


def _no_material(state: Any) -> bool:
    facets = state.facets
    return facets.session == "no_session" and facets.material == "missing"


def _material_inventory_needed(state: Any) -> bool:
    return state.facets.material == "inventory_needed"


def _research_needed(state: Any) -> bool:
    return state.facets.evidence in {"research_needed", "durable_research_needed"}


def _human_needed(state: Any) -> bool:
    facets = state.facets
    return facets.claims == "conflict" or facets.interaction == "human_needed"


def _repair_needed(state: Any) -> bool:
    return state.facets.quality == "repairable"


def _quality_hard_gate_failed(state: Any) -> bool:
    return state.facets.quality == "hard_gate_failed"


def _ready_for_human_finalization(state: Any) -> bool:
    return state.facets.quality == "human_finalization_candidate" and state.hard_gates.status in {"pass", "unknown"}


def _draft_blocked_by_notice(state: Any) -> bool:
    facets = state.facets
    return (
        facets.material == "inventoried_sufficient"
        and facets.source_digest == "ready"
        and facets.claims == "validated"
        and facets.evidence == "supported"
        and facets.writing == "not_allowed"
    )


def _ready_for_drafting(state: Any) -> bool:
    return state.facets.writing == "drafting_allowed"


def _draft_exists_without_quality_readiness(state: Any) -> bool:
    return state.facets.session in {"draft_available", "compiled"}


READINESS_RULES = [
    ReadinessRule(_hard_gate_failed, "not_ready", "blocked", "Hard gate failures block readiness."),
    ReadinessRule(_author_override_conflicts, "not_ready", "blocked", "Author override conflicts with current evidence."),
    ReadinessRule(_strict_omx_missing, "not_ready", "blocked", "Strict OMX evidence is required but missing."),
    ReadinessRule(_figure_gate_blocks_final_readiness, "not_ready", "blocked", "Figure gate prevents final readiness."),
    ReadinessRule(_no_material, "needs_material", "blocked", "No session or material has been provided."),
    ReadinessRule(_material_inventory_needed, "material_inventory_needed", "blocked", "Material must be inventoried before drafting."),
    ReadinessRule(_research_needed, "research_needed", "blocked", "Machine-solvable evidence work remains."),
    ReadinessRule(_human_needed, "human_needed", "blocked", "Author judgment is required."),
    ReadinessRule(_repair_needed, "repair_needed", "blocked", "Repair loop is required."),
    ReadinessRule(_quality_hard_gate_failed, "not_ready", "blocked", "Quality hard gate failed."),
    ReadinessRule(_ready_for_human_finalization, "ready_for_human_finalization", "ready", "Automation is ready for human finalization."),
    ReadinessRule(_draft_blocked_by_notice, "draft_blocked", "blocked", "Prewriting notice must be shown before drafting."),
    ReadinessRule(_ready_for_drafting, "ready_for_drafting", "ready", "Drafting is allowed by current state."),
    ReadinessRule(_draft_exists_without_quality_readiness, "not_ready", "blocked", "Draft exists but claim-safe quality readiness is not established."),
]
