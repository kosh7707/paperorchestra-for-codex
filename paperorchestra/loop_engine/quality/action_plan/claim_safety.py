from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_plan.citation_integrity import _append_citation_integrity_actions
from paperorchestra.loop_engine.quality.action_plan.citation_quality import _append_citation_quality_actions
from paperorchestra.loop_engine.quality.action_plan.citation_support import _append_citation_support_actions
from paperorchestra.loop_engine.quality.action_plan.claim_review import (
    _append_high_risk_claim_actions,
    _append_planning_satisfaction_actions,
)
from paperorchestra.loop_engine.quality.action_plan.figure_grounding import _append_figure_grounding_actions
from paperorchestra.loop_engine.quality.action_plan.source_material import (
    _append_source_material_fidelity_actions,
    _append_source_obligation_actions,
)


def _append_tier2_claim_safety_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    if not isinstance(tier2, dict):
        return
    checks = tier2.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}
    _append_figure_grounding_actions(actions, checks.get("figure_grounding"))
    _append_citation_support_actions(actions, checks.get("citation_support_critic"))
    _append_citation_quality_actions(actions, checks.get("citation_quality_gate"))
    _append_citation_integrity_actions(actions, checks.get("citation_integrity_gate"))
    _append_source_material_fidelity_actions(actions, checks.get("source_material_fidelity"))
    _append_source_obligation_actions(actions, checks.get("source_obligations"))
    _append_high_risk_claim_actions(actions, checks.get("high_risk_claim_sweep"))
    _append_planning_satisfaction_actions(actions, checks.get("planning_satisfaction"))
