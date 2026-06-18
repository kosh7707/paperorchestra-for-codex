from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.action_core import _action
from paperorchestra.loop_engine.quality.citation_gap import _citation_support_gap_classification
from paperorchestra.loop_engine.quality.policy import CITATION_SUPPORT_REVIEW_REFRESH_CODES


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
