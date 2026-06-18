from __future__ import annotations

from typing import Any

from .policy import QA_LOOP_SUPPORTED_HANDLER_CODES


def _human_handoff(verdict: str, actions: list[dict[str, Any]], quality_eval: dict[str, Any]) -> dict[str, Any] | None:
    if verdict not in {"human_needed", "ready_for_human_finalization", "failed"}:
        return None
    human_codes = [str(action.get("code")) for action in actions if action.get("automation") == "human_needed"]
    tier4 = ((quality_eval.get("tiers") or {}).get("tier_4_human_finalization") or {}) if isinstance(quality_eval.get("tiers"), dict) else {}
    return {
        "reason": verdict,
        "human_action_codes": human_codes,
        "tier_4_outstanding_owners": tier4.get("outstanding_owners", []),
    }


def _next_ralph_instruction(verdict: str, actions: list[dict[str, Any]]) -> str:
    if verdict == "ready_for_human_finalization":
        return "Stop automatic writing: Tier 0-3 are ready, but final figures, proof rigor, bibliography curation, venue fit, and submission remain human-owned."
    if verdict == "failed":
        return "Stop: quality loop budget/progress guards failed. Escalate the repeated hard-gate failure or oscillation to a human operator."
    if verdict == "human_needed":
        return "Stop automatic editing and request human judgment for the remaining human-needed repair actions."
    executable = [
        action
        for action in actions
        if action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) in QA_LOOP_SUPPORTED_HANDLER_CODES
    ]
    first = executable[0] if executable else actions[0] if actions else {}
    commands = first.get("suggested_commands") or []
    command_text = " Then run: " + " && ".join(commands) if commands else ""
    if executable:
        return f"Continue with executable action {first.get('code', 'the first repair action')}: {first.get('ralph_instruction', '')}{command_text}"
    return "Do not continue automatically: no qa-loop-step-supported repair action remains."
