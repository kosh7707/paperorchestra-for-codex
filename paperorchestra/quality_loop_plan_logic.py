from __future__ import annotations

from pathlib import Path
from typing import Any

from .quality_loop_actions import _action
from .quality_loop_history import _failing_codes_from_quality_eval, _tier_statuses
from .quality_loop_policy import (
    HARD_HUMAN_ACTION_CODES,
    NON_REVIEWABLE_ACTION_CODES,
    NON_REVIEWABLE_TIER1_CODES,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    REVIEW_REFRESH_CODES,
)
from .quality_loop_utils import _path_ref


def _quality_eval_actions(quality_eval: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return actions
    tier0 = tiers.get("tier_0_preconditions") if isinstance(tiers.get("tier_0_preconditions"), dict) else {}
    if isinstance(tier0, dict):
        for code in tier0.get("failing_codes") or []:
            if str(code) not in {
                "narrative_plan_missing",
                "claim_map_missing",
                "citation_placement_plan_missing",
                "narrative_plan_stale",
                "claim_map_stale",
                "citation_placement_plan_stale",
            }:
                continue
            actions.append(
                _action(
                    action_id=f"quality-eval:{code}",
                    code=str(code),
                    source=None,
                    target="narrative planning artifacts",
                    automation="automatic",
                    reason="Fresh narrative/claim/citation placement planning artifacts are required before claim-safe writing or evaluation.",
                    suggested_commands=["paperorchestra plan-narrative", "paperorchestra quality-eval --quality-mode claim_safe"],
                    ralph_instruction="Regenerate planning artifacts with `paperorchestra plan-narrative`; do not continue automated writing against missing or stale plans.",
                )
            )
    tier1 = tiers.get("tier_1_structural") if isinstance(tiers.get("tier_1_structural"), dict) else {}
    if isinstance(tier1, dict):
        for code in tier1.get("failing_codes") or []:
            if str(code) not in {
                "compile_report_missing",
                "compile_report_stale",
                "compile_report_legacy_untrusted",
                "compile_pdf_missing",
                "compile_pdf_stale",
                "compile_not_clean",
            }:
                continue
            actions.append(
                _action(
                    action_id=f"quality-eval:{code}",
                    code=str(code),
                    source=((tier1.get("checks") or {}).get("compile_clean") or {}).get("source")
                    if isinstance((tier1.get("checks") or {}).get("compile_clean"), dict)
                    else None,
                    target="compile",
                    automation="automatic",
                    reason="Claim-safe readiness requires a clean compile report for the current manuscript hash.",
                    suggested_commands=["paperorchestra compile", "paperorchestra quality-eval --quality-mode claim_safe"],
                    ralph_instruction="Compile the current manuscript and require the compile report manuscript hash to match paper.full.tex before continuing.",
                )
            )
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    citation_check = (tier2.get("checks") or {}).get("citation_support_critic") if isinstance(tier2, dict) else None
    if isinstance(citation_check, dict):
        citation_codes = set(citation_check.get("failing_codes") or [])
        if citation_codes & {"citation_support_review_missing", "citation_support_review_stale"}:
            code = "citation_support_review_stale" if "citation_support_review_stale" in citation_codes else "citation_support_review_missing"
            actions.append(
                _action(
                    action_id="quality-eval:citation-support",
                    code=code,
                    source=citation_check.get("path"),
                    target="claim safety",
                    automation="automatic",
                    reason="Claim-safe mode requires a current orthogonal citation-support critic before reviewer scores can be trusted.",
                    suggested_commands=["paperorchestra review-citations --evidence-mode web", "paperorchestra qa-loop-plan --quality-mode claim_safe"],
                    ralph_instruction="Run the citation-support critic for the current manuscript with the writer blind to reviewer scores, then rebuild the QA loop plan.",
                )
            )
        if {
            "citation_support_unsupported",
            "citation_support_contradicted",
            "citation_support_weak",
            "citation_support_manual_check",
            "citation_support_metadata_only",
            "citation_support_insufficient_evidence",
            "citation_support_evidence_missing",
            "citation_support_review_legacy_untrusted",
            "citation_support_summary_mismatch",
            "citation_support_claim_count_mismatch",
            "citation_support_sentence_coverage_mismatch",
            "citation_support_citation_map_stale",
            "citation_support_invalid_status",
            "citation_support_non_web_supported",
            "citation_support_untrusted_web_provenance",
            "citation_support_trace_missing",
            "citation_support_trace_mismatch",
            "citation_support_trace_invalid",
        } & citation_codes:
            actions.append(
                _action(
                    action_id="quality-eval:citation-support-weak",
                    code="citation_support_critic_failed",
                    source=citation_check.get("path"),
                    target="claim safety",
                    automation="semi_auto",
                    reason="Citation-support critic found unsupported or weakly supported cited claims.",
                    suggested_commands=["paperorchestra review-citations --evidence-mode web", "paperorchestra write-sections", "paperorchestra validate-current"],
                    ralph_instruction="Produce a candidate claim-safe rewrite only from existing verified citations, then require citation-support critic approval.",
                    why_not_automatic="Resolving unsupported citations can alter factual claims; writer cannot decide source support alone.",
                    approval_required_from="citation_support_critic",
                )
            )
    citation_integrity_check = (tier2.get("checks") or {}).get("citation_integrity_gate") if isinstance(tier2, dict) else None
    if isinstance(citation_integrity_check, dict):
        integrity_codes = {str(code) for code in citation_integrity_check.get("failing_codes") or []}
        stale_or_missing_codes = {
            "rendered_reference_audit_missing",
            "rendered_reference_audit_stale",
            "citation_intent_plan_missing",
            "citation_intent_plan_stale",
            "citation_source_match_missing",
            "citation_source_match_stale",
            "citation_integrity_missing",
            "citation_integrity_stale",
            "citation_critic_missing",
            "citation_critic_stale",
        }
        if integrity_codes & stale_or_missing_codes:
            code = sorted(integrity_codes & stale_or_missing_codes)[0]
            actions.append(
                _action(
                    action_id="quality-eval:citation-integrity-refresh",
                    code=code,
                    source=(citation_integrity_check.get("citation_integrity_audit") or {}).get("path")
                    if isinstance(citation_integrity_check.get("citation_integrity_audit"), dict)
                    else None,
                    target="citation integrity evidence",
                    automation="automatic",
                    reason="Claim-safe mode requires citation-integrity artifacts bound to the current manuscript and citation-support review.",
                    suggested_commands=[
                        "paperorchestra audit-rendered-references --quality-mode claim_safe",
                        "paperorchestra audit-citation-integrity --quality-mode claim_safe",
                        "paperorchestra audit-citation-integrity-critic --quality-mode claim_safe",
                        "paperorchestra qa-loop-plan --quality-mode claim_safe",
                    ],
                    ralph_instruction="Refresh rendered-reference and citation-integrity artifacts for the current manuscript before evaluating claim-safe readiness.",
                )
            )
        density_codes = {"citation_bomb_detected", "citation_integrity_audit_fail", "citation_integrity_failed", "citation_critic_failed"}
        if integrity_codes & density_codes:
            actions.append(
                _action(
                    action_id="quality-eval:citation-density",
                    code="citation_density_policy_failed",
                    source=(citation_integrity_check.get("citation_integrity_audit") or {}).get("path")
                    if isinstance(citation_integrity_check.get("citation_integrity_audit"), dict)
                    else None,
                    target="citation density and source-use discipline",
                    automation="human_needed",
                    reason="Citation-integrity critic found citation-density, duplicate-support, source-match, or context-policy failures that need claim-preserving source-use judgment.",
                    suggested_commands=[
                        "paperorchestra audit-citation-integrity --quality-mode claim_safe",
                        "paperorchestra review-citations --evidence-mode web",
                        "paperorchestra quality-eval --quality-mode claim_safe",
                    ],
                    ralph_instruction="Do not silence citation-integrity failures. Split citation-bomb sentences, remove redundant references, or scope claims while preserving citation-support critic approval.",
                    approval_required_from="citation_integrity_critic",
                )
            )
    source_check = (tier2.get("checks") or {}).get("source_material_fidelity") if isinstance(tier2, dict) else None
    if isinstance(source_check, dict) and source_check.get("status") == "fail":
        actions.append(
            _action(
                action_id="quality-eval:source-material-fidelity",
                code="source_material_coverage_insufficient",
                source=None,
                target="source-material fidelity",
                automation="semi_auto",
                reason="The manuscript omits required proof/results material that appears in the source packet or experiment log.",
                suggested_commands=[
                    "paperorchestra write-sections",
                    "paperorchestra review-sections",
                    "paperorchestra review-citations --evidence-mode web",
                    "paperorchestra qa-loop-plan --quality-mode claim_safe",
                ],
                ralph_instruction="Run one bounded evidence-backed rewrite/refinement pass that restores omitted proof or benchmark material without inventing new facts.",
                why_not_automatic="Restoring omitted technical content changes manuscript substance; the candidate must pass source-material, section, citation, validation, and compile critics.",
                approval_required_from="source_material_critic",
            )
        )
    obligation_check = (tier2.get("checks") or {}).get("source_obligations") if isinstance(tier2, dict) else None
    if isinstance(obligation_check, dict):
        obligation_codes = {str(code) for code in obligation_check.get("failing_codes") or []}
        if obligation_codes & {"source_obligations_missing", "source_obligations_stale", "source_obligations_legacy_untrusted"}:
            code = "source_obligations_stale" if "source_obligations_stale" in obligation_codes else "source_obligations_missing"
            actions.append(
                _action(
                    action_id=f"quality-eval:{code}",
                    code=code,
                    source=obligation_check.get("path"),
                    target="source obligations",
                    automation="automatic",
                    reason="Claim-safe source-material fidelity requires a current source-obligations matrix for the session input packet.",
                    suggested_commands=["paperorchestra build-source-obligations", "paperorchestra quality-eval --quality-mode claim_safe"],
                    ralph_instruction="Regenerate source_obligations.json from the current snapshotted input packet before continuing claim-safe evaluation.",
                )
            )
        if obligation_codes & {"source_obligation_missing", "source_obligation_anchor_missing", "source_obligation_numeric_mismatch"}:
            actions.append(
                _action(
                    action_id="quality-eval:source-obligation-satisfaction",
                    code="source_material_coverage_insufficient",
                    source=obligation_check.get("path"),
                    target="source-material fidelity",
                    automation="semi_auto",
                    reason="The manuscript does not satisfy one or more source-material obligations.",
                    suggested_commands=["paperorchestra write-sections", "paperorchestra review-sections", "paperorchestra quality-eval --quality-mode claim_safe"],
                    ralph_instruction="Run one bounded evidence-backed rewrite/refinement pass that satisfies the missing source obligations without inventing new facts.",
                    why_not_automatic="Filling missing source obligations changes manuscript substance and must be checked by source/material critics.",
                    approval_required_from="source_material_critic",
                )
            )
    high_risk_check = (tier2.get("checks") or {}).get("high_risk_claim_sweep") if isinstance(tier2, dict) else None
    if isinstance(high_risk_check, dict) and high_risk_check.get("status") == "fail":
        actions.append(
            _action(
                action_id="quality-eval:high-risk-claim-sweep",
                code="high_risk_uncited_claim",
                source=None,
                target="claim safety",
                automation="human_needed",
                reason="High-risk uncited factual, novelty, security, benchmark, or numeric claims remain without citation, source-obligation support, or limitation scoping.",
                suggested_commands=["paperorchestra write-sections", "paperorchestra review-citations --evidence-mode web", "paperorchestra quality-eval --quality-mode claim_safe"],
                ralph_instruction="Stop automatic readiness: high-risk uncited claims need source/citation grounding or explicit limitation scoping.",
                approval_required_from="claim_safety_critic",
            )
        )
    planning_check = (tier2.get("checks") or {}).get("planning_satisfaction") if isinstance(tier2, dict) else None
    if isinstance(planning_check, dict) and planning_check.get("status") == "fail":
        actions.append(
            _action(
                action_id="quality-eval:planning-satisfaction",
                code="planning_satisfaction_failed",
                source=None,
                target="narrative/claim/citation plan satisfaction",
                automation="human_needed",
                reason="The manuscript does not satisfy current narrative, claim-map, or citation-placement obligations.",
                suggested_commands=["paperorchestra write-sections", "paperorchestra validate-current", "paperorchestra quality-eval --quality-mode claim_safe"],
                ralph_instruction="Plan satisfaction failures are substantive writing issues; implement a supported targeted rewrite handler before continuing automatically.",
                why_not_automatic="Naive automated rewriting can satisfy keyword gates dishonestly; requires a dedicated handler and critic approval.",
                approval_required_from="plan_satisfaction_critic",
            )
        )
    tier3 = tiers.get("tier_3_scholarly_quality") if isinstance(tiers.get("tier_3_scholarly_quality"), dict) else {}
    if isinstance(tier3, dict) and "review_score_missing" in (tier3.get("failing_codes") or []):
        actions.append(
            _action(
                action_id="quality-eval:review-score",
                code="review_score_missing",
                source=None,
                target="scholarly scorecard",
                automation="automatic",
                reason="Tier 3 scholarly quality cannot be evaluated until a reviewer artifact exists.",
                suggested_commands=["paperorchestra review", "paperorchestra qa-loop-plan"],
                ralph_instruction="Run the reviewer only after Tier 0-2 are pass/warn; do not expose numeric scores to the writer.",
            )
        )
    if isinstance(tier3, dict):
        failing = {str(code) for code in tier3.get("failing_codes") or []}
        review_refresh_codes = REVIEW_REFRESH_CODES
        for code in sorted(failing & review_refresh_codes):
            actions.append(
                _action(
                    action_id=f"quality-eval:{code}",
                    code=code,
                    source=((tier3.get("checks") or {}).get("review_scorecard") or {}).get("path")
                    if isinstance((tier3.get("checks") or {}).get("review_scorecard"), dict)
                    else None,
                    target="scholarly scorecard",
                    automation="automatic",
                    reason="Reviewer scorecard is missing current-manuscript provenance and cannot be trusted.",
                    suggested_commands=["paperorchestra review", "paperorchestra qa-loop-plan --quality-mode claim_safe"],
                    ralph_instruction="Regenerate the skeptical reviewer artifact for the current manuscript before using Tier 3.",
                )
            )
        if failing & {"review_overall_below_threshold", "review_axis_below_threshold"}:
            actions.append(
                _action(
                    action_id="quality-eval:review-score-low",
                    code="review_score_below_threshold",
                    source=((tier3.get("checks") or {}).get("review_scorecard") or {}).get("path")
                    if isinstance((tier3.get("checks") or {}).get("review_scorecard"), dict)
                    else None,
                    target="scholarly quality",
                    automation="semi_auto",
                    reason="The reviewer scorecard says the manuscript is not strong enough for human-finalization readiness.",
                    suggested_commands=["paperorchestra refine --iterations 1", "paperorchestra review", "paperorchestra qa-loop-plan --quality-mode claim_safe"],
                    ralph_instruction="Run one bounded refinement pass using redacted reviewer issues, then regenerate reviewer and section critics.",
                    why_not_automatic="Refinement changes manuscript substance; accept only when validation, compile, citation support, and critic scores do not regress.",
                    approval_required_from="reviewer_and_section_critic",
                )
            )
        section_check = (tier3.get("checks") or {}).get("section_quality_critic")
        if isinstance(section_check, dict):
            section_codes = {str(code) for code in section_check.get("failing_codes") or []}
            for code in sorted(section_codes & {"section_review_missing", "section_review_stale", "section_review_legacy_untrusted"}):
                actions.append(
                    _action(
                        action_id=f"quality-eval:{code}",
                        code=code,
                        source=section_check.get("path"),
                        target="section quality critic",
                        automation="automatic",
                        reason="Section-level critic is missing or stale for the current manuscript.",
                        suggested_commands=["paperorchestra review-sections", "paperorchestra qa-loop-plan --quality-mode claim_safe"],
                        ralph_instruction="Run the deterministic section critic for the current manuscript before deciding HITL readiness.",
                    )
                )
            if "section_process_residue_detected" in section_codes:
                actions.append(
                    _action(
                        action_id="quality-eval:section-process-residue",
                        code="section_process_residue_detected",
                        source=section_check.get("path"),
                        target="section quality",
                        automation="human_needed",
                        reason="Section-level critic found reviewer-visible process residue; this is a non-reviewable structural artifact.",
                        suggested_commands=["paperorchestra write-sections", "paperorchestra review-sections", "paperorchestra qa-loop-plan --quality-mode claim_safe"],
                        ralph_instruction="Stop and regenerate the affected manuscript prose; do not route process residue as ordinary human-needed feedback.",
                    )
                )
            if section_codes & {"section_review_empty", "section_quality_below_threshold", "section_required_fixes_pending"}:
                actions.append(
                    _action(
                        action_id="quality-eval:section-quality",
                        code="section_quality_below_threshold",
                        source=section_check.get("path"),
                        target="section quality",
                        automation="semi_auto",
                        reason="Section-level critic found shallow, low-score, or required-fix sections; this is not reviewable paper content yet.",
                        suggested_commands=[
                            "paperorchestra review",
                            "paperorchestra refine --iterations 1",
                            "paperorchestra review-sections",
                            "paperorchestra qa-loop-plan --quality-mode claim_safe",
                        ],
                        ralph_instruction="Run one bounded content refinement pass from critic issues, then regenerate section and reviewer critics before continuing.",
                        why_not_automatic="Improving weak sections changes manuscript substance; acceptance requires non-regression across validation, compile, citation support, and critic checks.",
                        approval_required_from="section_quality_critic",
                    )
                )
        independence_check = (tier3.get("checks") or {}).get("reviewer_independence")
        if isinstance(independence_check, dict) and independence_check.get("status") == "fail":
            actions.append(
                _action(
                    action_id="quality-eval:reviewer-independence",
                    code="reviewer_independence_missing",
                    source=(independence_check.get("acceptance") or {}).get("path") if isinstance(independence_check.get("acceptance"), dict) else None,
                    target="scholarly quality",
                    automation="human_needed",
                    reason="Claim-safe readiness requires an independent reviewer artifact pair or an explicit reviewer-independence acceptance record.",
                    suggested_commands=[
                        "paperorchestra review --output review.independent.json",
                        "paperorchestra quality-eval --quality-mode claim_safe",
                    ],
                    ralph_instruction="Stop before ready_for_human_finalization: obtain a second independent review or record a hash-bound human acceptance artifact.",
                    approval_required_from="human_operator",
                )
            )
    return actions

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
