from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action
from paperorchestra.loop_engine.quality.citation_gap import _citation_support_gap_classification
from paperorchestra.loop_engine.quality.policy import CITATION_SUPPORT_REVIEW_REFRESH_CODES


def _append_tier2_claim_safety_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    if not isinstance(tier2, dict):
        return
    checks = tier2.get("checks") or {}
    if not isinstance(checks, dict):
        checks = {}
    _append_figure_grounding_actions(actions, checks.get("figure_grounding"))
    _append_citation_support_actions(actions, checks.get("citation_support_critic"))
    _append_citation_quality_actions(actions, checks.get("citation_quality_gate"))
    _append_citation_integrity_actions(actions, checks.get("citation_integrity_gate"))
    _append_source_material_fidelity_actions(actions, checks.get("source_material_fidelity"))
    _append_source_obligation_actions(actions, checks.get("source_obligations"))
    _append_high_risk_claim_actions(actions, checks.get("high_risk_claim_sweep"))
    _append_planning_satisfaction_actions(actions, checks.get("planning_satisfaction"))

def _append_figure_grounding_actions(actions: list[dict[str, Any]], figure_check: Any) -> None:
    if isinstance(figure_check, dict):
        issue_items = [
            item
            for item in figure_check.get("figures") or []
            if isinstance(item, dict) and item.get("failing_codes")
        ]
        if not issue_items:
            issue_items = [{"label": "figure grounding", "failing_codes": figure_check.get("failing_codes") or []}]
        for item in issue_items:
            label = str(item.get("label") or "figure grounding")
            section = str(item.get("section_title") or "")
            assets = ", ".join(str(asset) for asset in item.get("included_assets") or [] if str(asset).strip())
            context = str(item.get("nearby_reference_context") or "").strip()
            manifest = item.get("plot_manifest_match") if isinstance(item.get("plot_manifest_match"), dict) else {}
            for code in [str(code) for code in item.get("failing_codes") or [] if str(code).strip()]:
                target = f"{label}" + (f" in {section}" if section else "")
                detail = (
                    (f" Assets: {assets}." if assets else "")
                    + (f" Nearby context: {context[:180]}." if context else "")
                    + (f" Manifest purpose/title: {manifest.get('purpose') or manifest.get('title')}." if manifest else "")
                )
                actions.append(
                    _action(
                        action_id=f"quality-eval:figure-grounding:{code}:{len(actions)+1}",
                        code=code,
                        source=figure_check.get("path"),
                        target=target,
                        automation="human_needed",
                        reason=f"Figure-placement review failed for {target} with {code}; claim-safe readiness requires critic/operator judgment before changing visual evidence or captions.{detail}",
                        suggested_commands=[
                            "paperorchestra critique",
                            "paperorchestra answer-human-needed --answer <answer>",
                            "paperorchestra qa-loop --quality-mode claim_safe",
                        ],
                        ralph_instruction=(
                            "Do not route unsafe figure/caption grounding to automatic repair. Ask a figure-placement critic/operator to remove, "
                            "replace, or recaption the affected figure, then rerun review-figure-placement."
                        ),
                        why_not_automatic="Changing figure placement, captions, or visual evidence can alter paper meaning and requires figure-grounding critic/operator approval.",
                        approval_required_from="figure_placement_review_critic",
                    )
                )

def _append_citation_support_actions(actions: list[dict[str, Any]], citation_check: Any) -> None:
    if isinstance(citation_check, dict):
        citation_codes = set(citation_check.get("failing_codes") or [])
        for code in sorted(citation_codes & CITATION_SUPPORT_REVIEW_REFRESH_CODES):
            actions.append(
                _action(
                    action_id=f"quality-eval:citation-support:{code}",
                    code=code,
                    source=citation_check.get("path"),
                    target="claim safety",
                    automation="automatic",
                    reason="Claim-safe mode requires a current orthogonal citation-support critic before reviewer scores can be trusted.",
                    suggested_commands=["paperorchestra critique --citation-evidence-mode web", "paperorchestra qa-loop --quality-mode claim_safe"],
                    ralph_instruction="Run the citation-support critic for the current manuscript with the writer blind to reviewer scores, then rebuild the QA loop plan.",
                )
            )
        citation_repair_codes = {
            "citation_support_unsupported",
            "citation_support_contradicted",
            "citation_support_weak",
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
        }
        manual_check = _citation_support_gap_classification(citation_check) if citation_codes & {"citation_support_manual_check", "citation_support_weak"} else {
            "machine_solvable_count": 0,
            "machine_research_needed_count": 0,
            "author_judgment_count": 0,
            "payload_unavailable": False,
        }
        machine_research_count = int(manual_check.get("machine_research_needed_count") or 0)
        weak_author_marker_count = int(manual_check.get("weak_author_marker_count") or 0)
        if machine_research_count > 0:
            actions.append(
                _action(
                    action_id="quality-eval:citation-support-evidence-research",
                    code="citation_support_evidence_research_needed",
                    source=citation_check.get("path"),
                    target="citation support evidence",
                    automation="automatic",
                    reason=f"{machine_research_count} citation-support manual-check item(s) have concrete but unbound evidence surfaces and must be re-verified by search before author judgment.",
                    suggested_commands=[
                        "paperorchestra critique --citation-evidence-mode web",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Refresh citation-support evidence with web/S2-backed verification for the machine-solvable unbound evidence surfaces before attempting rewrite or asking the author.",
                )
            )
        repair_codes_for_current_gap = set(citation_repair_codes & citation_codes)
        if machine_research_count > 0 or weak_author_marker_count > 0:
            repair_codes_for_current_gap.discard("citation_support_weak")
        if repair_codes_for_current_gap or int(manual_check.get("machine_solvable_count") or 0) > 0:
            machine_manual_count = int(manual_check.get("machine_solvable_count") or 0)
            manual_phrase = (
                f" {machine_manual_count} manual-check item(s) have concrete fixes and support evidence for bounded repair."
                if machine_manual_count
                else ""
            )
            actions.append(
                _action(
                    action_id="quality-eval:citation-support-weak",
                    code="citation_support_critic_failed",
                    source=citation_check.get("path"),
                    target="claim safety",
                    automation="semi_auto",
                    reason="Citation-support critic found cited-claim support failures that can be attempted by bounded repair." + manual_phrase,
                    suggested_commands=["paperorchestra critique --citation-evidence-mode web", "paperorchestra write-sections", "paperorchestra quality-gate --no-fail-on-block"],
                    ralph_instruction="Produce a candidate claim-safe rewrite only from existing verified citations and machine-solvable manual-check issue counts, then require citation-support critic approval.",
                    why_not_automatic="Resolving unsupported citations can alter factual claims; writer cannot decide source support alone.",
                    approval_required_from="citation_support_critic",
                )
            )
        if (
            ("citation_support_manual_check" in citation_codes and int(manual_check.get("manual_author_judgment_count") or manual_check.get("author_judgment_count") or 0) > 0)
            or weak_author_marker_count > 0
            or ("citation_support_manual_check" in citation_codes and manual_check.get("payload_unavailable") is True)
        ):
            author_count = int(manual_check.get("manual_author_judgment_count") or manual_check.get("author_judgment_count") or 0)
            if weak_author_marker_count:
                author_count += weak_author_marker_count
            unavailable = manual_check.get("payload_unavailable") is True
            reason = (
                "Citation-support manual-check payload is unavailable for safe machine classification."
                if unavailable
                else f"{author_count} citation-support manual-check item(s) require author/operator judgment."
            )
            actions.append(
                _action(
                    action_id="quality-eval:citation-support-manual-author",
                    code="citation_support_manual_check_requires_author_judgment",
                    source=citation_check.get("path"),
                    target="claim safety",
                    automation="human_needed",
                    reason=reason,
                    suggested_commands=[
                        "paperorchestra answer-human-needed --answer <answer>",
                        "paperorchestra critique --citation-evidence-mode web",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction=(
                        "Stop automatic promotion for the author-owned citation-support manual-check item count. "
                        "Ask the author/operator to decide whether to provide evidence, soften/delete the claim, or accept responsibility."
                    ),
                    why_not_automatic="Manual-check items without concrete support evidence or with explicit author-judgment markers cannot be resolved by the writer alone.",
                    approval_required_from="author_operator",
                )
            )

def _append_citation_quality_actions(actions: list[dict[str, Any]], citation_quality_gate: Any) -> None:
    if isinstance(citation_quality_gate, dict):
        quality_codes = {str(code) for code in citation_quality_gate.get("hard_gate_failures") or []}
        refresh_codes = {"citation_quality_stale", "citation_quality_manuscript_missing"}
        critical_codes = {
            "critical_unknown_reference",
            "critical_missing_bib_entry",
            "critical_unsupported_citation",
            "critical_citation_support_missing",
            "critical_weak_reference_identity",
        }
        for code in sorted(quality_codes & refresh_codes):
            actions.append(
                _action(
                    action_id=f"quality-eval:citation-quality:{code}",
                    code=code,
                    source=None,
                    target="citation quality evidence",
                    automation="automatic",
                    reason="Claim-safe citation quality needs fresh artifacts bound to the current manuscript before source support can be trusted.",
                    suggested_commands=[
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra critique --citation-evidence-mode web",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Refresh citation-quality artifacts for the current manuscript before evaluating claim-safe readiness.",
                )
            )
        for code in sorted(quality_codes & critical_codes):
            actions.append(
                _action(
                    action_id=f"quality-eval:citation-quality:{code}",
                    code=code,
                    source=None,
                    target="citation quality",
                    automation="semi_auto",
                    reason="Critical citation quality failed; resolve with machine citation support/search evidence before asking the author for final source-use judgment.",
                    suggested_commands=[
                        "paperorchestra critique --citation-evidence-mode web",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Do not route machine-solvable citation/source gaps to human_needed. Gather citation support or weaken/delete unsupported claims, then rerun citation quality.",
                    why_not_automatic="Changing cited support can alter factual claims, so the rewrite is semi-automatic but the evidence search remains machine-solvable first.",
                    approval_required_from="citation_quality_gate",
                )
            )

def _append_citation_integrity_actions(actions: list[dict[str, Any]], citation_integrity_check: Any) -> None:
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
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Refresh rendered-reference and citation-integrity artifacts for the current manuscript before evaluating claim-safe readiness.",
                )
            )
        density_codes = {
            "citation_bomb_detected",
            "citation_duplicate_support",
            "citation_integrity_audit_fail",
            "citation_integrity_failed",
            "citation_critic_failed",
        }
        if integrity_codes & density_codes:
            actions.append(
                _action(
                    action_id="quality-eval:citation-density",
                    code="citation_density_policy_failed",
                    source=(citation_integrity_check.get("citation_integrity_audit") or {}).get("path")
                    if isinstance(citation_integrity_check.get("citation_integrity_audit"), dict)
                    else None,
                    target="citation density and source-use discipline",
                    automation="semi_auto",
                    reason="Citation-integrity critic found citation-density, duplicate-support, source-match, or context-policy failures that should be repaired before asking the author for final judgment.",
                    suggested_commands=[
                        "paperorchestra qa-loop-step",
                        "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                        "paperorchestra critique --citation-evidence-mode web",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Produce a bounded citation-integrity repair candidate: split dense citation bundles, remove redundant repeated support, or scope claims while preserving citation-support critic approval.",
                    why_not_automatic="Changing citation placement can alter claim support boundaries; the candidate must remain uncommitted until citation-integrity critic approval.",
                    approval_required_from="citation_integrity_critic",
                )
            )

def _append_source_material_fidelity_actions(actions: list[dict[str, Any]], source_check: Any) -> None:
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
                    "paperorchestra critique",
                    "paperorchestra critique --citation-evidence-mode web",
                    "paperorchestra qa-loop --quality-mode claim_safe",
                ],
                ralph_instruction="Run one bounded evidence-backed rewrite/refinement pass that restores omitted proof or benchmark material without inventing new facts.",
                why_not_automatic="Restoring omitted technical content changes manuscript substance; the candidate must pass source-material, section, citation, validation, and compile critics.",
                approval_required_from="source_material_critic",
            )
        )

def _append_source_obligation_actions(actions: list[dict[str, Any]], obligation_check: Any) -> None:
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
                    suggested_commands=["paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
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
                    suggested_commands=["paperorchestra write-sections", "paperorchestra critique", "paperorchestra qa-loop --quality-mode claim_safe"],
                    ralph_instruction="Run one bounded evidence-backed rewrite/refinement pass that satisfies the missing source obligations without inventing new facts.",
                    why_not_automatic="Filling missing source obligations changes manuscript substance and must be checked by source/material critics.",
                    approval_required_from="source_material_critic",
                )
            )

def _append_high_risk_claim_actions(actions: list[dict[str, Any]], high_risk_check: Any) -> None:
    if isinstance(high_risk_check, dict) and high_risk_check.get("status") == "fail":
        actions.append(
            _action(
                action_id="quality-eval:high-risk-claim-sweep",
                code="high_risk_uncited_claim",
                source=None,
                target="claim safety",
                automation="semi_auto",
                reason="High-risk uncited factual, novelty, security, benchmark, or numeric claims remain without citation, source-obligation support, or limitation scoping.",
                suggested_commands=[
                    "paperorchestra qa-loop-step",
                    "paperorchestra critique --citation-evidence-mode web",
                    "paperorchestra quality-gate --quality-mode claim_safe --no-fail-on-block",
                    "paperorchestra qa-loop --quality-mode claim_safe",
                ],
                ralph_instruction="Ground each high-risk uncited claim with existing verified evidence, scope it as a limitation/author-material claim, or delete it; do not add new claims or bibliography keys.",
                why_not_automatic="Repairing high-risk claims can alter factual substance; the candidate must be checked by claim-safety/citation critics before promotion.",
                approval_required_from="claim_safety_critic",
            )
        )

def _append_planning_satisfaction_actions(actions: list[dict[str, Any]], planning_check: Any) -> None:
    if isinstance(planning_check, dict) and planning_check.get("status") == "fail":
        actions.append(
            _action(
                action_id="quality-eval:planning-satisfaction",
                code="planning_satisfaction_failed",
                source=None,
                target="narrative/claim/citation plan satisfaction",
                automation="human_needed",
                reason="The manuscript does not satisfy current narrative, claim-map, or citation-placement obligations.",
                suggested_commands=["paperorchestra write-sections", "paperorchestra quality-gate --no-fail-on-block", "paperorchestra qa-loop --quality-mode claim_safe"],
                ralph_instruction="Plan satisfaction failures are substantive writing issues; implement a supported targeted rewrite handler before continuing automatically.",
                why_not_automatic="Naive automated rewriting can satisfy keyword gates dishonestly; requires a dedicated handler and critic approval.",
                approval_required_from="plan_satisfaction_critic",
            )
        )
