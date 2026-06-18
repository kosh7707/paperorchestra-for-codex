from __future__ import annotations

from typing import Any

from .plan_verdict_context import PlanVerdictContext
from .policy import HARD_HUMAN_ACTION_CODES


def _human_needed_verdict(context: PlanVerdictContext, actions: list[dict[str, Any]]) -> tuple[str, str] | None:
    if (context.regression.get("oscillation") or {}).get("detected"):
        return "human_needed", "oscillation detected across recent quality-loop iterations"
    if (
        context.failing_codes
        and context.budget.get("current_attempt_consumes_budget")
        and not context.regression.get("forward_progress", True)
    ):
        return "human_needed", "the latest budgeted qa-loop step made no forward progress"
    if context.regression.get("tier_3_axis_drops"):
        return "human_needed", "Tier 3 reviewer-axis regression exceeded tolerance"
    repeated = context.regression.get("repeated_actionable_failure")
    if isinstance(repeated, dict) and repeated.get("detected"):
        signature = repeated.get("signature") if isinstance(repeated.get("signature"), dict) else {}
        reason = signature.get("reason") or "same actionable repair failure"
        return "human_needed", f"repeated actionable repair failure detected: {reason}"
    tier3 = context.tiers.get("tier_3_scholarly_quality") if isinstance(context.tiers.get("tier_3_scholarly_quality"), dict) else {}
    if tier3.get("anti_inflation_triggered"):
        return "human_needed", "reviewer score anti-inflation guard triggered"
    if any(action.get("automation") == "human_needed" and action.get("code") in HARD_HUMAN_ACTION_CODES for action in actions):
        return "human_needed", "a hard human-needed provenance or manual-review blocker is present"
    return None
