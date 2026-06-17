from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.quality.artifact_checks import (
    _figure_grounding_check,
    _ralph_evidence_check,
)
from paperorchestra.loop_engine.quality.citation_support import _citation_support_check
from paperorchestra.loop_engine.quality.history import _build_cross_iteration
from paperorchestra.loop_engine.quality.leakage import (
    PDF_TEXT_SCAN_UNAVAILABLE_CODE,
    _manuscript_prompt_leakage,
    _manuscript_prompt_leakage_report,
)
from paperorchestra.loop_engine.quality.policy import (
    DEFAULT_MAX_ITERATIONS,
    MODE_THRESHOLDS,
    QUALITY_EVAL_SCHEMA_VERSION,
    QUALITY_MODES,
    TIER2_CLAIM_CODES,
)
from paperorchestra.loop_engine.quality.provenance import (
    _mixed_provenance_acceptance,
    _mixed_provenance_acceptance_path,
    _provenance_trust,
)
from paperorchestra.loop_engine.quality.eval_preconditions import PreconditionContext, build_precondition_tier
from paperorchestra.loop_engine.quality.eval_tiers import (
    _skipped_tier,
    _status_from_failures,
    _strict_issue_codes,
    _tier,
)
from paperorchestra.loop_engine.quality.reviews import (
    _review_score_check,
    _reviewer_independence_check,
    _section_quality_check,
    _validation_issue_counts,
)
from paperorchestra.loop_engine.quality.source_checks import (
    _high_risk_claim_sweep,
    _planning_satisfaction_check,
    _source_material_fidelity_check,
)
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists, _sha256_jsonable
from paperorchestra.manuscript.narrative import planning_artifact_status
from paperorchestra.manuscript.source_obligations import evaluate_source_obligations, source_obligations_path
from paperorchestra.reviews.citation_integrity import (
    citation_integrity_audit_path,
    citation_integrity_check,
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
    rendered_reference_audit_path,
)
from paperorchestra.reviews.citation_quality import build_citation_quality_gate_internal, citation_quality_gate_path
from paperorchestra.reviews.fidelity import build_reproducibility_audit, run_fidelity_audit


def _normalize_quality_mode(mode: str | None) -> str:
    normalized = (mode or "ralph").strip().lower().replace("-", "_")
    if normalized not in QUALITY_MODES:
        raise ValueError(f"Unknown quality mode {mode!r}; expected one of: {', '.join(sorted(QUALITY_MODES))}")
    return normalized


def build_quality_eval(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    require_live_verification: bool = False,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    reproducibility: dict[str, Any] | None = None,
    fidelity: dict[str, Any] | None = None,
    current_attempt_consumes_budget: bool = False,
) -> dict[str, Any]:
    mode = _normalize_quality_mode(quality_mode)
    state = load_session(cwd)
    reproducibility = reproducibility if reproducibility is not None else build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    fidelity = fidelity if fidelity is not None else run_fidelity_audit(cwd)
    manuscript_hash = _file_sha256(state.artifacts.paper_full_tex)
    citation_support_review_path = _citation_support_path(cwd, state)
    citation_support_review_sha256 = _file_sha256(citation_support_review_path)
    ralph_evidence = _ralph_evidence_check(cwd, quality_mode=mode)
    provenance = _provenance_trust(reproducibility)

    paper_exists = bool(state.artifacts.paper_full_tex and Path(state.artifacts.paper_full_tex).exists())
    planning_status = planning_artifact_status(cwd)
    tier0_result = build_precondition_tier(
        PreconditionContext(
            paper_full_tex=state.artifacts.paper_full_tex,
            paper_exists=paper_exists,
            manuscript_hash=manuscript_hash,
            reproducibility=reproducibility,
            planning_status=planning_status,
        )
    )
    tier0 = tier0_result.tier

    tiers: dict[str, Any] = {"tier_0_preconditions": tier0}
    if getattr(_manuscript_prompt_leakage, "__module__", "") == "paperorchestra.loop_engine.quality.leakage":
        leakage_report = _manuscript_prompt_leakage_report(state)
        leakage = leakage_report["markers"]
        pdf_text_scan_unavailable = leakage_report["pdf_text_scan_unavailable"]
    else:
        # Tests and downstream integrators have historically patched
        # `quality_loop._manuscript_prompt_leakage` to isolate higher-tier
        # quality gates.  Preserve that seam: a patched leakage scanner owns
        # the prompt/PDF leakage surface for that invocation.
        leakage = _manuscript_prompt_leakage(state)
        pdf_text_scan_unavailable = []
    non_reviewable = {
        "status": "fail" if leakage else "pass",
        "failing_codes": ["prompt_meta_leakage"] if leakage else [],
        "checks": {
            "prompt_meta_leakage": {"status": "fail" if leakage else "pass", "markers": leakage},
        },
    }
    if tier0["status"] == "fail":
        tiers["tier_1_structural"] = _skipped_tier("tier_0_preconditions failed")
        tiers["tier_2_claim_safety"] = _skipped_tier("tier_0_preconditions failed")
        tiers["tier_3_scholarly_quality"] = _skipped_tier("tier_0_preconditions failed")
    else:
        tier1_failing: list[str] = []
        compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
        compile_check: dict[str, Any] = {
            "source": state.artifacts.latest_compile_report_json,
            "expected_manuscript_sha256": manuscript_hash,
        }
        compile_status = "pass"
        if not isinstance(compile_report, dict):
            compile_status = "fail" if mode == "claim_safe" else "warn"
            compile_check.update({"status": compile_status, "reason": "compile_report_missing"})
            if mode == "claim_safe":
                tier1_failing.append("compile_report_missing")
        else:
            actual_compile_hash = compile_report.get("manuscript_sha256")
            compile_check.update(
                {
                    "clean": compile_report.get("clean"),
                    "manuscript_sha256": actual_compile_hash,
                    "expected_manuscript_sha256": manuscript_hash,
                    "pdf_sha256": compile_report.get("pdf_sha256"),
                    "actual_pdf_sha256": _file_sha256(compile_report.get("pdf_path")),
                    "pdf_path": compile_report.get("pdf_path"),
                    "pdf_exists": compile_report.get("pdf_exists"),
                }
            )
            if mode == "claim_safe" and not actual_compile_hash:
                compile_status = "fail"
                compile_check.update({"status": "fail", "reason": "compile_report_legacy_untrusted"})
                tier1_failing.append("compile_report_legacy_untrusted")
            elif actual_compile_hash and manuscript_hash and actual_compile_hash != manuscript_hash:
                compile_status = "fail"
                compile_check.update({"status": "fail", "reason": "compile_report_stale"})
                tier1_failing.append("compile_report_stale")
            elif not compile_report.get("clean"):
                compile_status = "fail"
                compile_check.update({"status": "fail", "reason": "compile_not_clean"})
                tier1_failing.append("compile_not_clean")
            elif mode == "claim_safe" and not _file_sha256(compile_report.get("pdf_path")):
                compile_status = "fail"
                compile_check.update({"status": "fail", "reason": "compile_pdf_missing"})
                tier1_failing.append("compile_pdf_missing")
            elif (
                mode == "claim_safe"
                and compile_report.get("pdf_sha256")
                and _file_sha256(compile_report.get("pdf_path")) != compile_report.get("pdf_sha256")
            ):
                compile_status = "fail"
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
        tier1 = _tier(
            status=_status_from_failures(tier1_failing),
            checks={
                "compile_clean": compile_check,
                "citation_key_integrity": {"status": "pass" if not citation_issues else "fail", "issues": citation_issues},
                "prompt_meta_leakage": {"status": "pass" if not leakage else "fail", "markers": leakage},
                "pdf_text_scan": {
                    "status": "fail"
                    if mode == "claim_safe" and pdf_text_scan_unavailable
                    else ("warn" if pdf_text_scan_unavailable else "pass"),
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
        tiers["tier_1_structural"] = tier1

        if tier1["status"] == "fail":
            tiers["tier_2_claim_safety"] = _skipped_tier("tier_1_structural failed")
            tiers["tier_3_scholarly_quality"] = _skipped_tier("tier_1_structural failed")
        else:
            claim_counts = _validation_issue_counts(reproducibility)
            citation_support = _citation_support_check(cwd, state, quality_mode=mode)
            citation_integrity = citation_integrity_check(cwd, state, quality_mode=mode)
            citation_quality = build_citation_quality_gate_internal(cwd, quality_mode=mode)
            source_material = _source_material_fidelity_check(state)
            figure_grounding = _figure_grounding_check(state)
            source_obligations = evaluate_source_obligations(cwd)
            high_risk_claims = _high_risk_claim_sweep(state, source_obligations)
            planning_satisfaction = _planning_satisfaction_check(state, planning_status)
            tier2_failing: list[str] = []
            for code in sorted(TIER2_CLAIM_CODES):
                if claim_counts.get(code, 0) > 0:
                    tier2_failing.append(code)
            tier2_failing.extend(citation_support.get("failing_codes") or [])
            tier2_failing.extend(citation_integrity.get("failing_codes") or [])
            tier2_failing.extend(citation_quality.get("hard_gate_failures") or [])
            tier2_failing.extend(figure_grounding.get("failing_codes") or [])
            tier2_failing.extend(ralph_evidence.get("failing_codes") or [])
            tier2_failing.extend(source_material.get("failing_codes") or [])
            tier2_failing.extend(source_obligations.get("failing_codes") or [])
            tier2_failing.extend(high_risk_claims.get("failing_codes") or [])
            tier2_failing.extend(planning_satisfaction.get("failing_codes") or [])
            if citation_support.get("status") == "fail":
                for code in citation_support.get("failing_codes") or []:
                    if code in {"citation_support_review_missing", "citation_support_review_stale"}:
                        tier2_failing.append(code)
            tier2_warn_only = mode == "draft"
            tier2 = _tier(
                status=_status_from_failures(tier2_failing, warn_only=tier2_warn_only),
                checks={
                    "unsupported_comparative_claims": {
                        "status": "fail" if claim_counts.get("unsupported_comparative_claim", 0) else "pass",
                        "count": claim_counts.get("unsupported_comparative_claim", 0),
                    },
                    "numeric_grounding": {
                        "status": "fail" if claim_counts.get("numeric_grounding_mismatch", 0) else "pass",
                        "count": claim_counts.get("numeric_grounding_mismatch", 0),
                    },
                    "citation_support_critic": citation_support,
                    "citation_integrity_gate": citation_integrity,
                    "citation_quality_gate": citation_quality,
                    "figure_grounding": figure_grounding,
                    "ralph_evidence": ralph_evidence,
                    "source_material_fidelity": source_material,
                    "source_obligations": source_obligations,
                    "high_risk_claim_sweep": high_risk_claims,
                    "planning_satisfaction": planning_satisfaction,
                    "experiment_log_consistency": {"status": "not_automated", "owner": "human_or_domain_critic"},
                },
                failing_codes=tier2_failing,
                mode_effect=("warning_in_draft" if tier2_warn_only and tier2_failing else "hard_fail_in_claim_safe" if tier2_failing else "pass"),
            )
            tiers["tier_2_claim_safety"] = tier2

            if tier2["status"] == "fail":
                tiers["tier_3_scholarly_quality"] = _skipped_tier("tier_2_claim_safety failed in claim-safe mode")
            else:
                review_check = _review_score_check(state, quality_mode=mode)
                section_check = _section_quality_check(cwd, state, quality_mode=mode)
                reviewer_independence = _reviewer_independence_check(cwd, state, quality_mode=mode)
                thresholds = MODE_THRESHOLDS[mode]
                tier3_failing: list[str] = []
                tier3_failing.extend(review_check.get("failing_codes") or [])
                tier3_failing.extend(section_check.get("failing_codes") or [])
                tier3_failing.extend(reviewer_independence.get("failing_codes") or [])
                overall_score = review_check.get("overall_score")
                axis_scores = review_check.get("axis_scores") if isinstance(review_check.get("axis_scores"), dict) else {}
                anti = review_check.get("anti_inflation_violations") or []
                tier3_status = _status_from_failures(tier3_failing, warn_only=True)
                tiers["tier_3_scholarly_quality"] = _tier(
                    status=tier3_status,
                    checks={
                        "scorecard_available": {
                            "status": "pass" if review_check.get("status") == "pass" else "warn",
                            "source": review_check.get("path"),
                        },
                        "review_scorecard": review_check,
                        "section_quality_critic": section_check,
                        "reviewer_independence": reviewer_independence,
                        "thresholds": thresholds,
                        "writer_score_visibility": {"status": "pass", "writer_receives_scores": False, "operator_only": True},
                    },
                    failing_codes=tier3_failing,
                    overall_score=overall_score,
                    axis_scores=axis_scores,
                    anti_inflation_triggered=bool(review_check.get("anti_inflation_triggered")),
                    anti_inflation_violations=anti,
                )

    tiers["tier_4_human_finalization"] = {
        "status": "never_automated",
        "outstanding_owners": [
            {"area": "final_figures", "owner": "human"},
            {"area": "proof_rigor", "owner": "human"},
            {"area": "bibliography_curation", "owner": "human"},
            {"area": "venue_fit", "owner": "human"},
            {"area": "submission_decision", "owner": "human"},
        ],
    }

    payload: dict[str, Any] = {
        "schema_version": QUALITY_EVAL_SCHEMA_VERSION,
        "manuscript_hash": f"sha256:{manuscript_hash}" if manuscript_hash else None,
        "evaluated_at": utc_now_iso(),
        "session_id": state.session_id,
        "mode": mode,
        "provenance_trust": provenance,
        "non_reviewable": non_reviewable,
        "tiers": tiers,
        "cross_iteration": {},
        "source_artifacts": {
            "paper_full_tex": state.artifacts.paper_full_tex,
            "reproducibility_audit": state.artifacts.latest_reproducibility_json,
            "fidelity_audit": state.artifacts.latest_fidelity_json,
            "figure_placement_review": state.artifacts.latest_figure_placement_review_json,
            "latest_validation": state.artifacts.latest_validation_json,
            "latest_review": state.artifacts.latest_review_json,
            "latest_section_review": getattr(state.artifacts, "latest_section_review_json", None),
            "narrative_plan": state.artifacts.narrative_plan_json,
            "claim_map": state.artifacts.claim_map_json,
            "citation_placement_plan": state.artifacts.citation_placement_plan_json,
            "source_obligations": str(source_obligations_path(cwd)),
            "citation_support_review": str(citation_support_review_path),
            "citation_review_sha256": citation_support_review_sha256,
            "citation_integrity_audit": str(citation_integrity_audit_path(cwd)),
            "citation_integrity_audit_sha256": _file_sha256(citation_integrity_audit_path(cwd)),
            "citation_integrity_critic": str(citation_integrity_critic_path(cwd)),
            "citation_integrity_critic_sha256": _file_sha256(citation_integrity_critic_path(cwd)),
            "citation_intent_plan": str(citation_intent_plan_path(cwd)),
            "citation_intent_plan_sha256": _file_sha256(citation_intent_plan_path(cwd)),
            "citation_source_match": str(citation_source_match_path(cwd)),
            "citation_source_match_sha256": _file_sha256(citation_source_match_path(cwd)),
            "rendered_reference_audit": str(rendered_reference_audit_path(cwd)),
            "rendered_reference_audit_sha256": _file_sha256(rendered_reference_audit_path(cwd)),
            "citation_quality_gate_sha256": _file_sha256(citation_quality_gate_path(cwd)),
            "ralph_handoff": ralph_evidence["ralph_handoff"],
            "ralph_handoff_sha256": ralph_evidence["ralph_handoff_sha256"],
            "qa_loop_history": ralph_evidence["qa_loop_history"],
            "qa_loop_history_sha256": ralph_evidence["qa_loop_history_sha256"],
        },
        "audit_snapshot_hashes": {
            "reproducibility": f"sha256:{_sha256_jsonable(reproducibility)}",
            "fidelity": f"sha256:{_sha256_jsonable(fidelity)}",
        },
    }
    failing_codes = _failing_codes_from_quality_eval(payload)
    tier3_payload = tiers.get("tier_3_scholarly_quality") if isinstance(tiers.get("tier_3_scholarly_quality"), dict) else {}
    current_axis_scores = tier3_payload.get("axis_scores") if isinstance(tier3_payload, dict) and isinstance(tier3_payload.get("axis_scores"), dict) else {}
    payload["cross_iteration"] = _build_cross_iteration(
        cwd,
        state.session_id,
        payload.get("manuscript_hash"),
        failing_codes,
        max_iterations,
        current_axis_scores=current_axis_scores,
        current_attempt_consumes_budget=current_attempt_consumes_budget,
    )
    return payload
