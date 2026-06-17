from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action


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
