from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_builders import _quality_eval_actions
from .history import _failing_codes_from_quality_eval, _tier_statuses
from .policy import (
    HARD_HUMAN_ACTION_CODES,
    NON_REVIEWABLE_ACTION_CODES,
    NON_REVIEWABLE_TIER1_CODES,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
)
from .utils import _path_ref


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

def _plan_reads(quality_eval_path: str | Path | None, quality_eval: dict[str, Any]) -> dict[str, Any]:
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval.get("source_artifacts"), dict) else {}
    citation_support_path = source_artifacts.get("citation_support_review")
    citation_support = {
        "path": str(citation_support_path) if citation_support_path else None,
        "ref": _path_ref(citation_support_path),
        "sha256": source_artifacts.get("citation_review_sha256"),
        "current_sha256": source_artifacts.get("citation_review_current_sha256"),
        "identity_status": source_artifacts.get("citation_review_identity_status"),
    }
    return {
        "quality_eval": _path_ref(quality_eval_path),
        "validation": _path_ref(source_artifacts.get("latest_validation")),
        "fidelity": _path_ref(source_artifacts.get("fidelity_audit")),
        "reproducibility": _path_ref(source_artifacts.get("reproducibility_audit")),
        "figure_placement": _path_ref(source_artifacts.get("figure_placement_review")),
        "citation_support": citation_support,
        "citation_integrity": {
            "audit": _path_ref(source_artifacts.get("citation_integrity_audit")),
            "audit_sha256": source_artifacts.get("citation_integrity_audit_sha256"),
            "critic": _path_ref(source_artifacts.get("citation_integrity_critic")),
            "critic_sha256": source_artifacts.get("citation_integrity_critic_sha256"),
            "rendered_reference_audit": _path_ref(source_artifacts.get("rendered_reference_audit")),
            "rendered_reference_audit_sha256": source_artifacts.get("rendered_reference_audit_sha256"),
        },
        "ralph": {
            "handoff": _path_ref(source_artifacts.get("ralph_handoff")),
            "handoff_sha256": source_artifacts.get("ralph_handoff_sha256"),
            "qa_loop_history": _path_ref(source_artifacts.get("qa_loop_history")),
            "qa_loop_history_sha256": source_artifacts.get("qa_loop_history_sha256"),
        },
        "section_review": _path_ref(source_artifacts.get("latest_section_review")),
        "source_obligations": _path_ref(source_artifacts.get("source_obligations")),
        "narrative_plan": _path_ref(source_artifacts.get("narrative_plan")),
        "claim_map": _path_ref(source_artifacts.get("claim_map")),
        "citation_placement_plan": _path_ref(source_artifacts.get("citation_placement_plan")),
    }

def _quality_eval_summary_for_plan(quality_eval: dict[str, Any]) -> dict[str, Any]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier_statuses = _tier_statuses(quality_eval)
    return {
        "schema_version": quality_eval.get("schema_version"),
        "mode": quality_eval.get("mode"),
        "manuscript_hash": quality_eval.get("manuscript_hash"),
        "tier_statuses": tier_statuses,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "provenance_level": (quality_eval.get("provenance_trust") or {}).get("level"),
        "writer_score_visibility": ((tiers.get("tier_3_scholarly_quality") or {}).get("checks") or {}).get(
            "writer_score_visibility",
            {"status": "pass", "writer_receives_scores": False, "operator_only": True},
        ),
    }

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
