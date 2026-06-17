from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action
from paperorchestra.loop_engine.quality.policy import REVIEW_REFRESH_CODES


def _append_tier3_scholarly_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
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
                suggested_commands=["paperorchestra critique", "paperorchestra qa-loop"],
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
                    suggested_commands=["paperorchestra critique", "paperorchestra qa-loop --quality-mode claim_safe"],
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
                    suggested_commands=["paperorchestra qa-loop-step", "paperorchestra critique", "paperorchestra qa-loop --quality-mode claim_safe"],
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
                        suggested_commands=["paperorchestra critique", "paperorchestra qa-loop --quality-mode claim_safe"],
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
                        suggested_commands=["paperorchestra write-sections", "paperorchestra critique", "paperorchestra qa-loop --quality-mode claim_safe"],
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
                            "paperorchestra critique",
                            "paperorchestra qa-loop-step",
                            "paperorchestra critique",
                            "paperorchestra qa-loop --quality-mode claim_safe",
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
                        "paperorchestra critique --output-dir <critic-run-dir>",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Stop before ready_for_human_finalization: obtain a second independent review or record a hash-bound human acceptance artifact.",
                    approval_required_from="human_operator",
                )
            )
