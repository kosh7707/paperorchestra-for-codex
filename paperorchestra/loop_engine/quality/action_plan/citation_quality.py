from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action


def _append_citation_quality_actions(actions: list[dict[str, Any]], citation_quality_gate: Any) -> None:
    if not isinstance(citation_quality_gate, dict):
        return

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
