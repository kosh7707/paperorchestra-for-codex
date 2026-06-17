from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action
from paperorchestra.loop_engine.quality.action_plan.citation_integrity import _append_citation_integrity_actions
from paperorchestra.loop_engine.quality.action_plan.citation_quality import _append_citation_quality_actions
from paperorchestra.loop_engine.quality.action_plan.citation_support import _append_citation_support_actions


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
