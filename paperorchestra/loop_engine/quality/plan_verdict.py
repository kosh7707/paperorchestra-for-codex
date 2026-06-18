from __future__ import annotations

from typing import Any

from .history import _failing_codes_from_quality_eval
from .policy import (
    HARD_HUMAN_ACTION_CODES,
    NON_REVIEWABLE_ACTION_CODES,
    NON_REVIEWABLE_TIER1_CODES,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
)


def _quality_eval_ready(quality_eval: dict[str, Any], *, accept_mixed_provenance: bool) -> bool:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return False
    for key in ("tier_0_preconditions", "tier_1_structural", "tier_2_claim_safety"):
        if not isinstance(tiers.get(key), dict) or tiers[key].get("status") != "pass":
            return False
    tier3 = tiers.get("tier_3_scholarly_quality")
    if not isinstance(tier3, dict) or tier3.get("status") != "pass":
        return False
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    provenance_level = provenance.get("level")
    mixed_acceptance = provenance.get("mixed_acceptance") if isinstance(provenance.get("mixed_acceptance"), dict) else {}
    return provenance_level == "live" or (
        provenance_level == "mixed"
        and accept_mixed_provenance
        and mixed_acceptance.get("status") == "pass"
    )


def _plan_verdict(
    quality_eval: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    accept_mixed_provenance: bool,
) -> tuple[str, str]:
    cross = quality_eval.get("cross_iteration") or {}
    budget = cross.get("budget") or {}
    regression = cross.get("regression") or {}
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    failing_codes = _failing_codes_from_quality_eval(quality_eval)
    tier0_codes = set((tiers.get("tier_0_preconditions") or {}).get("failing_codes") or []) if isinstance(tiers.get("tier_0_preconditions"), dict) else set()
    tier1_codes = set((tiers.get("tier_1_structural") or {}).get("failing_codes") or []) if isinstance(tiers.get("tier_1_structural"), dict) else set()
    if int(budget.get("remaining") or 0) <= 0 and failing_codes:
        return "failed", "iteration budget exhausted before the quality loop reached human-finalization readiness"
    non_reviewable_codes = (
        set((quality_eval.get("non_reviewable") or {}).get("failing_codes") or [])
        if isinstance(quality_eval.get("non_reviewable"), dict)
        else set()
    )
    if (tier1_codes | non_reviewable_codes) & NON_REVIEWABLE_TIER1_CODES:
        return "failed", "non-reviewable structural artifact: prompt/meta leakage reached the manuscript, generated assets, or compiled PDF"
    if any(str(action.get("code")) in NON_REVIEWABLE_ACTION_CODES for action in actions):
        return "failed", "non-reviewable structural artifact: generated placeholder figures are still used in the review candidate"
    if failing_codes and not regression.get("forward_progress", True) and (tier0_codes or tier1_codes):
        return "failed", "the same Tier 0/1 failure set repeated without forward progress"
    if (regression.get("oscillation") or {}).get("detected"):
        return "human_needed", "oscillation detected across recent quality-loop iterations"
    if (
        failing_codes
        and budget.get("current_attempt_consumes_budget")
        and not regression.get("forward_progress", True)
    ):
        return "human_needed", "the latest budgeted qa-loop step made no forward progress"
    if regression.get("tier_3_axis_drops"):
        return "human_needed", "Tier 3 reviewer-axis regression exceeded tolerance"
    repeated_failure = regression.get("repeated_actionable_failure") if isinstance(regression.get("repeated_actionable_failure"), dict) else {}
    if repeated_failure.get("detected"):
        signature = repeated_failure.get("signature") if isinstance(repeated_failure.get("signature"), dict) else {}
        reason = signature.get("reason") or "same actionable repair failure"
        return "human_needed", f"repeated actionable repair failure detected: {reason}"
    tier3 = tiers.get("tier_3_scholarly_quality") if isinstance(tiers.get("tier_3_scholarly_quality"), dict) else {}
    if isinstance(tier3, dict) and tier3.get("anti_inflation_triggered"):
        return "human_needed", "reviewer score anti-inflation guard triggered"
    if any(action.get("automation") == "human_needed" and action.get("code") in HARD_HUMAN_ACTION_CODES for action in actions):
        return "human_needed", "a hard human-needed provenance or manual-review blocker is present"
    if _quality_eval_ready(quality_eval, accept_mixed_provenance=accept_mixed_provenance) and not actions:
        return "ready_for_human_finalization", "Tier 0-3 passed and provenance is acceptable; Tier 4 remains human-owned"
    executable_actions = [action for action in actions if action.get("automation") in {"automatic", "semi_auto"}]
    supported_executable_actions = [
        action for action in executable_actions if str(action.get("code")) in QA_LOOP_SUPPORTED_HANDLER_CODES
    ]
    if supported_executable_actions:
        return "continue", "automatic or semi-automatic repair actions remain within the iteration budget"
    if executable_actions:
        return "human_needed", "repair actions exist, but no qa-loop-step handler is available for them yet"
    if any(action.get("automation") == "human_needed" for action in actions):
        return "human_needed", "only human/domain-judgment actions remain"
    return "human_needed", "quality evaluation is not ready but no safe automatic repair action remains"
