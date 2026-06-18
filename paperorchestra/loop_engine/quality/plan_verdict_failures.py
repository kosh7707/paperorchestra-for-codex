from __future__ import annotations

from typing import Any

from .plan_verdict_context import PlanVerdictContext
from .policy import NON_REVIEWABLE_ACTION_CODES, NON_REVIEWABLE_TIER1_CODES


def _failed_verdict(context: PlanVerdictContext, actions: list[dict[str, Any]]) -> tuple[str, str] | None:
    if int(context.budget.get("remaining") or 0) <= 0 and context.failing_codes:
        return "failed", "iteration budget exhausted before the quality loop reached human-finalization readiness"
    if (context.tier1_codes | context.non_reviewable_codes) & NON_REVIEWABLE_TIER1_CODES:
        return "failed", "non-reviewable structural artifact: prompt/meta leakage reached the manuscript, generated assets, or compiled PDF"
    if any(str(action.get("code")) in NON_REVIEWABLE_ACTION_CODES for action in actions):
        return "failed", "non-reviewable structural artifact: generated placeholder figures are still used in the review candidate"
    if context.failing_codes and not context.regression.get("forward_progress", True) and (context.tier0_codes or context.tier1_codes):
        return "failed", "the same Tier 0/1 failure set repeated without forward progress"
    return None
