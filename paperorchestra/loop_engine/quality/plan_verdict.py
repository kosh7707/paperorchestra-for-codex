from __future__ import annotations

from typing import Any

from .plan_readiness import _quality_eval_ready
from .plan_verdict_context import PlanVerdictContext
from .policy import (
    HARD_HUMAN_ACTION_CODES,
    NON_REVIEWABLE_ACTION_CODES,
    NON_REVIEWABLE_TIER1_CODES,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
)


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


def _action_verdict(actions: list[dict[str, Any]]) -> tuple[str, str]:
    executable = [action for action in actions if action.get("automation") in {"automatic", "semi_auto"}]
    supported = [action for action in executable if str(action.get("code")) in QA_LOOP_SUPPORTED_HANDLER_CODES]
    if supported:
        return "continue", "automatic or semi-automatic repair actions remain within the iteration budget"
    if executable:
        return "human_needed", "repair actions exist, but no qa-loop-step handler is available for them yet"
    if any(action.get("automation") == "human_needed" for action in actions):
        return "human_needed", "only human/domain-judgment actions remain"
    return "human_needed", "quality evaluation is not ready but no safe automatic repair action remains"


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
