from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.actions import _action


def _append_tier0_precondition_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
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
                    suggested_commands=["paperorchestra run --provider shell", "paperorchestra qa-loop --quality-mode claim_safe"],
                    ralph_instruction="Regenerate planning artifacts through the high-level run/orchestrator path; do not continue automated writing against missing or stale plans.",
                )
            )

def _append_tier1_structural_actions(actions: list[dict[str, Any]], tiers: dict[str, Any]) -> None:
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
                    suggested_commands=["paperorchestra compile", "paperorchestra qa-loop --quality-mode claim_safe"],
                    ralph_instruction="Compile the current manuscript and require the compile report manuscript hash to match paper.full.tex before continuing.",
                )
            )
        for code in tier1.get("failing_codes") or []:
            if str(code) != "pdf_text_scan_unavailable":
                continue
            actions.append(
                _action(
                    action_id="quality-eval:pdf_text_scan_unavailable",
                    code="pdf_text_scan_unavailable",
                    source=None,
                    target="PDF text leakage scan",
                    automation="human_needed",
                    reason="Claim-safe readiness requires extracting compiled PDF text before PaperOrchestra can prove prompt/meta leakage did not reach the rendered manuscript.",
                    suggested_commands=[
                        "apt-get install -y poppler-utils  # or: sudo apt-get install -y poppler-utils",
                        "PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile",
                        "paperorchestra qa-loop --quality-mode claim_safe",
                    ],
                    ralph_instruction="Do not rewrite the manuscript for this blocker. Install or expose pdftotext/poppler-utils, recompile, and rebuild quality-eval so the rendered PDF text can be scanned.",
                    why_not_automatic="This is an execution-environment dependency, not a manuscript repair; automated rewriting cannot prove rendered-PDF leakage without pdftotext.",
                )
            )
