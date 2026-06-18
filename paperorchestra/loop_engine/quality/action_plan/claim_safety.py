from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_plan import citation_integrity as _citation_integrity
from paperorchestra.loop_engine.quality.action_plan import citation_quality as _citation_quality
from paperorchestra.loop_engine.quality.action_plan import citation_support as _citation_support
from paperorchestra.loop_engine.quality.action_plan import claim_review as _claim_review
from paperorchestra.loop_engine.quality.action_plan import figure_grounding as _figure_grounding
from paperorchestra.loop_engine.quality.action_plan import source_material as _source_material


def _append_tier2_claim_safety_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    if not isinstance(tier2, dict):
        return
    checks = tier2.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}
    _figure_grounding._append_figure_grounding_actions(actions, checks.get("figure_grounding"))
    _citation_support._append_citation_support_actions(actions, checks.get("citation_support_critic"))
    _citation_quality._append_citation_quality_actions(actions, checks.get("citation_quality_gate"))
    _citation_integrity._append_citation_integrity_actions(actions, checks.get("citation_integrity_gate"))
    _source_material._append_source_material_fidelity_actions(actions, checks.get("source_material_fidelity"))
    _source_material._append_source_obligation_actions(actions, checks.get("source_obligations"))
    _claim_review._append_high_risk_claim_actions(actions, checks.get("high_risk_claim_sweep"))
    _claim_review._append_planning_satisfaction_actions(actions, checks.get("planning_satisfaction"))
