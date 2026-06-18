from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.leakage import PDF_TEXT_SCAN_UNAVAILABLE_CODE
from paperorchestra.loop_engine.quality.eval_tiers import _status_from_failures, _tier
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


def build_structural_tier(
    *,
    state,
    mode: str,
    manuscript_hash: str | None,
    reproducibility: dict[str, Any],
    leakage: list[str],
    pdf_text_scan_unavailable: list[str],
) -> dict[str, Any]:
    tier1_failing: list[str] = []
    compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
    compile_check: dict[str, Any] = {
        "source": state.artifacts.latest_compile_report_json,
        "expected_manuscript_sha256": manuscript_hash,
    }
    if not isinstance(compile_report, dict):
        compile_status = "fail" if mode == "claim_safe" else "warn"
        compile_check.update({"status": compile_status, "reason": "compile_report_missing"})
        if mode == "claim_safe":
            tier1_failing.append("compile_report_missing")
    else:
        actual_compile_hash = compile_report.get("manuscript_sha256")
        actual_pdf_sha = _file_sha256(compile_report.get("pdf_path"))
        compile_check.update(
            {
                "clean": compile_report.get("clean"),
                "manuscript_sha256": actual_compile_hash,
                "expected_manuscript_sha256": manuscript_hash,
                "pdf_sha256": compile_report.get("pdf_sha256"),
                "actual_pdf_sha256": actual_pdf_sha,
                "pdf_path": compile_report.get("pdf_path"),
                "pdf_exists": compile_report.get("pdf_exists"),
            }
        )
        if mode == "claim_safe" and not actual_compile_hash:
            compile_check.update({"status": "fail", "reason": "compile_report_legacy_untrusted"})
            tier1_failing.append("compile_report_legacy_untrusted")
        elif actual_compile_hash and manuscript_hash and actual_compile_hash != manuscript_hash:
            compile_check.update({"status": "fail", "reason": "compile_report_stale"})
            tier1_failing.append("compile_report_stale")
        elif not compile_report.get("clean"):
            compile_check.update({"status": "fail", "reason": "compile_not_clean"})
            tier1_failing.append("compile_not_clean")
        elif mode == "claim_safe" and not actual_pdf_sha:
            compile_check.update({"status": "fail", "reason": "compile_pdf_missing"})
            tier1_failing.append("compile_pdf_missing")
        elif mode == "claim_safe" and compile_report.get("pdf_sha256") and actual_pdf_sha != compile_report.get("pdf_sha256"):
            compile_check.update({"status": "fail", "reason": "compile_pdf_stale"})
            tier1_failing.append("compile_pdf_stale")
        else:
            compile_check.update({"status": "pass"})
    citation_issues = reproducibility.get("citation_artifact_issues") or []
    if citation_issues:
        tier1_failing.append("citation_key_integrity")
    if leakage:
        tier1_failing.append("prompt_meta_leakage")
    if mode == "claim_safe" and pdf_text_scan_unavailable:
        tier1_failing.append(PDF_TEXT_SCAN_UNAVAILABLE_CODE)
    provenance_complete = int(reproducibility.get("prompt_trace_file_count") or 0) > 0
    if mode == "claim_safe" and pdf_text_scan_unavailable:
        pdf_text_scan_status = "fail"
    elif pdf_text_scan_unavailable:
        pdf_text_scan_status = "warn"
    else:
        pdf_text_scan_status = "pass"
    return _tier(
        status=_status_from_failures(tier1_failing),
        checks={
            "compile_clean": compile_check,
            "citation_key_integrity": {"status": "pass" if not citation_issues else "fail", "issues": citation_issues},
            "prompt_meta_leakage": {"status": "pass" if not leakage else "fail", "markers": leakage},
            "pdf_text_scan": {
                "status": pdf_text_scan_status,
                "markers": pdf_text_scan_unavailable,
                "orthogonal_to_prompt_meta_leakage": True,
                "next_steps": [
                    "Install poppler-utils or otherwise provide a working pdftotext binary.",
                    "Rerun: PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile",
                    "Rerun: paperorchestra qa-loop --quality-mode claim_safe",
                ]
                if pdf_text_scan_unavailable
                else [],
            },
            "provenance_complete": {
                "status": "pass" if provenance_complete else "warn",
                "prompt_trace_file_count": reproducibility.get("prompt_trace_file_count"),
                "orthogonal_to_tier_gates": True,
            },
        },
        failing_codes=tier1_failing,
    )
