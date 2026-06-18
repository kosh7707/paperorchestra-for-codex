from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_plan import claim_safety as _claim_safety
from paperorchestra.loop_engine.quality.action_plan import preconditions as _preconditions
from paperorchestra.loop_engine.quality.action_plan import scholarly as _scholarly


def _quality_eval_actions(quality_eval: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return actions
    _preconditions._append_tier0_precondition_actions(actions, tiers)
    _preconditions._append_tier1_structural_actions(actions, tiers)
    _claim_safety._append_tier2_claim_safety_actions(actions, tiers)
    _scholarly._append_tier3_scholarly_actions(actions, tiers)
    return actions
