from __future__ import annotations

from typing import Any

from .plan_readiness import _quality_eval_ready
from .plan_verdict_actions import _action_verdict
from .plan_verdict_context import PlanVerdictContext
from .plan_verdict_failures import _failed_verdict
from .plan_verdict_human_needed import _human_needed_verdict


def _plan_verdict(
    quality_eval: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    accept_mixed_provenance: bool,
) -> tuple[str, str]:
    context = PlanVerdictContext.from_quality_eval(quality_eval)
    for decision in (_failed_verdict(context, actions), _human_needed_verdict(context, actions)):
        if decision is not None:
            return decision
    if _quality_eval_ready(quality_eval, accept_mixed_provenance=accept_mixed_provenance) and not actions:
        return "ready_for_human_finalization", "Tier 0-3 passed and provenance is acceptable; Tier 4 remains human-owned"
    return _action_verdict(actions)
