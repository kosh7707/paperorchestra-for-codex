from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_plan.claim_safety import (
    _append_citation_integrity_actions,
    _append_citation_quality_actions,
    _append_citation_support_actions,
    _append_figure_grounding_actions,
    _append_high_risk_claim_actions,
    _append_planning_satisfaction_actions,
    _append_source_material_fidelity_actions,
    _append_source_obligation_actions,
    _append_tier2_claim_safety_actions,
)
from paperorchestra.loop_engine.quality.action_plan.preconditions import (
    _append_tier0_precondition_actions,
    _append_tier1_structural_actions,
)
from paperorchestra.loop_engine.quality.action_plan.scholarly import _append_tier3_scholarly_actions


def _quality_eval_actions(quality_eval: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return actions
    _append_tier0_precondition_actions(actions, tiers)
    _append_tier1_structural_actions(actions, tiers)
    _append_tier2_claim_safety_actions(actions, tiers)
    _append_tier3_scholarly_actions(actions, tiers)
    return actions
