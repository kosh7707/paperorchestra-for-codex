from __future__ import annotations

import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any

from .critics import citation_item_has_valid_supporting_evidence, extract_cited_sentences
from .citation_integrity import (
    citation_integrity_audit_path,
    citation_integrity_check,
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
    rendered_reference_audit_path,
)
from .fidelity import build_reproducibility_audit, run_fidelity_audit, write_reproducibility_audit
from .io_utils import read_json, write_json
from .models import utc_now_iso
from .narrative import planning_artifact_status
from .omx_diagnostics import OMX_EVIDENCE_SUMMARY_FILENAME, OMX_REVIEW_HANDOFF_FILENAME
from .providers import ShellProvider, get_citation_support_provider
from .session import artifact_path, load_session, runtime_root, save_session
from .source_obligations import evaluate_source_obligations, source_obligations_path
from .validator import check_citation_placement, check_claim_map_coverage, check_narrative_section_roles, extract_decimal_like_tokens

from .quality_loop_policy import (
    AUTO_REPAIR_CODES,
    BUDGET_CONSUMING_HISTORY_EVENTS,
    CITATION_SUPPORT_STATUSES,
    DEFAULT_MAX_ITERATIONS,
    FIGURE_REPAIR_CODES,
    HARD_HUMAN_ACTION_CODES,
    HISTORY_FILENAME,
    LEAKAGE_PATTERNS_ALWAYS,
    LEAKAGE_PATTERNS_VISUAL,
    MANUAL_REVIEW_CODES,
    MODE_THRESHOLDS,
    NON_REVIEWABLE_ACTION_CODES,
    NON_REVIEWABLE_TIER1_CODES,
    QA_LOOP_PLAN_SCHEMA_VERSION,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    QUALITY_EVAL_SCHEMA_VERSION,
    QUALITY_MODES,
    REQUIRED_REVIEW_AXES,
    REVIEW_REFRESH_CODES,
    SECTION_REVIEW_THRESHOLDS,
    SEMI_AUTO_REPAIR_CODES,
    TIER2_CLAIM_CODES,
)

from .quality_loop_history import (
    _build_cross_iteration,
    _failing_codes_from_quality_eval,
    _history_entry_consumes_budget,
    _read_quality_history,
    _resolve_axis_drop_tolerance,
    _tier_statuses,
    quality_loop_history_path,
)

from .quality_loop_leakage import (
    _leakage_markers_in_text,
    _manuscript_prompt_leakage,
    _pdf_text_for_prompt_leakage,
    _plot_asset_text_paths,
    _scan_text_file_for_prompt_leakage,
)

from .quality_loop_utils import _file_sha256, _path_ref, _read_json_if_exists, _sha256_jsonable
from .ralph_bridge_state import QA_LOOP_HANDOFF_FILENAME

from .quality_loop_citation_support import _citation_support_check, _citation_support_path
from .quality_loop_reviews import (
    _anti_inflation_violations,
    _current_review_records,
    _latest_review_payload,
    _nonempty_string,
    _numeric_axis_scores,
    _review_provenance_failures,
    _review_score_check,
    _review_shape_failures,
    _reviewer_acceptance_path,
    _reviewer_identity,
    _reviewer_independence_acceptance,
    _reviewer_independence_check,
    _section_quality_check,
    _section_review_path,
    _validation_issue_counts,
)
from .quality_loop_source_checks import (
    BENCHMARK_CLAIM_RE,
    HIGH_RISK_CLAIM_RE,
    LIMITATION_SCOPE_RE,
    SECURITY_CLAIM_RE,
    _high_risk_claim_sweep,
    _plainish_sentences,
    _planning_satisfaction_check,
    _read_text_if_exists,
    _sentence_supported_by_obligation,
    _source_material_fidelity_check,
)

from .quality_loop_actions import (
    _action,
    _automation_for_issue,
    _citation_actions,
    _claim_safety_approval,
    _commands_for_validation_issue,
    _dedupe_actions,
    _fidelity_actions,
    _figure_review_actions,
    _generated_placeholder_figure_actions,
    _mode_actions,
    _section_arg,
    _strict_content_actions,
    _target_section_from_stage,
    _validation_actions,
    _warning_actions,
)
from .quality_loop_plan_logic import (
    _human_handoff,
    _next_ralph_instruction,
    _plan_reads,
    _plan_verdict,
    _quality_eval_actions,
    _quality_eval_ready,
    _quality_eval_summary_for_plan,
)

def _normalize_quality_mode(mode: str | None) -> str:
    normalized = (mode or "ralph").strip().lower().replace("-", "_")
    if normalized not in QUALITY_MODES:
        raise ValueError(f"Unknown quality mode {mode!r}; expected one of: {', '.join(sorted(QUALITY_MODES))}")
    return normalized


def _strict_issue_codes(reproducibility: dict[str, Any], *, kinds: set[str] | None = None) -> list[str]:
    codes: list[str] = []
    for issue in reproducibility.get("strict_content_gate_issues") or []:
        if not isinstance(issue, dict):
            continue
        if kinds is not None and str(issue.get("kind") or "") not in kinds:
            continue
        code = str(issue.get("code") or "")
        if code:
            codes.append(code)
    return codes


def _tier(
    *,
    status: str,
    checks: dict[str, Any] | None = None,
    failing_codes: list[str] | None = None,
    skip_reason: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "checks": checks or {},
    }
    if failing_codes is not None:
        payload["failing_codes"] = sorted(dict.fromkeys(str(code) for code in failing_codes if code))
    if skip_reason:
        payload["skip_reason"] = skip_reason
    payload.update(extra)
    return payload


def _skipped_tier(reason: str) -> dict[str, Any]:
    return _tier(status="skipped_due_to_upstream_fail", checks={}, failing_codes=[], skip_reason=reason)


def _status_from_failures(failing_codes: list[str], *, warn_only: bool = False) -> str:
    if not failing_codes:
        return "pass"
    return "warn" if warn_only else "fail"















































































def _provenance_trust(reproducibility: dict[str, Any]) -> dict[str, Any]:
    mock_evidence: list[str] = []
    mixed_evidence: list[str] = []
    if reproducibility.get("latest_provider_name") == "mock":
        mock_evidence.append("provider_name=mock")
    if reproducibility.get("latest_verify_mode") == "mock":
        mock_evidence.append("verify_mode=mock")
    if reproducibility.get("latest_verify_fallback_used") == "mock":
        mock_evidence.append("verify_fallback_used=mock")
    if int(reproducibility.get("mock_registry_entry_count") or 0) > 0:
        mock_evidence.append(f"mock_registry_entry_count={reproducibility.get('mock_registry_entry_count')}")
    if int(reproducibility.get("prompt_trace_file_count") or 0) == 0:
        mixed_evidence.append("prompt_trace_missing")
    if (reproducibility.get("lane_manifest_summary") or {}).get("manifest_count", 0) == 0:
        mixed_evidence.append("lane_manifest_missing")
    if not reproducibility.get("verification_invoked"):
        mixed_evidence.append("live_verification_not_invoked")
    citation_live_provenance = reproducibility.get("citation_live_provenance")
    if isinstance(citation_live_provenance, dict):
        seed_only_count = int(citation_live_provenance.get("seed_only_count") or 0)
        if seed_only_count > 0:
            mixed_evidence.append(f"citation_registry_seed_only_count={seed_only_count}")
        status = str(citation_live_provenance.get("status") or "")
        if status in {"missing", "unreadable", "malformed", "empty"}:
            mixed_evidence.append(f"citation_live_provenance_status={status}")
    if mock_evidence:
        level = "mock"
    elif mixed_evidence or reproducibility.get("verdict") == "WARN":
        level = "mixed"
    else:
        level = "live"
    return {
        "level": level,
        "mock_evidence": mock_evidence,
        "mixed_evidence": mixed_evidence,
        "watermark_required": level != "live",
    }


def _mixed_provenance_acceptance_path(cwd: str | Path | None) -> Path:
    return runtime_root(cwd) / "mixed-provenance-acceptance.json"


def _mixed_provenance_acceptance(cwd: str | Path | None, quality_eval: dict[str, Any]) -> dict[str, Any]:
    path = _mixed_provenance_acceptance_path(cwd)
    payload = _read_json_if_exists(path)
    provenance = quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {}
    failures: list[str] = []
    if not isinstance(payload, dict):
        return {"status": "missing", "path": str(path), "failing_codes": ["mixed_provenance_acceptance_missing"]}
    if payload.get("schema_version") != "mixed-provenance-acceptance/1":
        failures.append("mixed_provenance_acceptance_legacy_untrusted")
    if payload.get("source") == "codex_operator" or payload.get("not_independent_human_review") is True:
        failures.append("mixed_provenance_acceptance_operator_not_independent")
    if payload.get("manuscript_sha256") != quality_eval.get("manuscript_hash"):
        failures.append("mixed_provenance_acceptance_stale")
    expected_provenance_sha = f"sha256:{_sha256_jsonable({k: v for k, v in provenance.items() if k != 'mixed_acceptance'})}"
    if payload.get("provenance_trust_sha256") != expected_provenance_sha:
        failures.append("mixed_provenance_acceptance_stale")
    if not str(payload.get("operator_label") or "").strip() or not str(payload.get("accepted_at") or "").strip():
        failures.append("mixed_provenance_acceptance_incomplete")
    if len(str(payload.get("rationale") or "").strip()) < 10:
        failures.append("mixed_provenance_acceptance_incomplete")
    return {
        "status": "fail" if failures else "pass",
        "path": str(path),
        "sha256": _file_sha256(path),
        "failing_codes": sorted(dict.fromkeys(failures)),
    }



def _ralph_evidence_check(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    handoff_path = artifact_path(cwd, QA_LOOP_HANDOFF_FILENAME)
    history_path = runtime_root(cwd) / HISTORY_FILENAME
    handoff = _read_json_if_exists(handoff_path)
    failing_codes: list[str] = []
    if quality_mode == "claim_safe":
        if not isinstance(handoff, dict):
            failing_codes.append("ralph_handoff_missing")
        else:
            contract = handoff.get("execution_contract") if isinstance(handoff.get("execution_contract"), dict) else {}
            if contract.get("ralph_required") is not True:
                failing_codes.append("ralph_handoff_not_required")
            if contract.get("critic_required") is not True:
                failing_codes.append("ralph_handoff_critic_not_required")
            if contract.get("citation_integrity_gate_required") is not True:
                failing_codes.append("ralph_handoff_citation_integrity_not_required")
        if not history_path.exists():
            failing_codes.append("qa_loop_history_missing")
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "ralph_handoff": str(handoff_path),
        "ralph_handoff_sha256": _file_sha256(handoff_path),
        "qa_loop_history": str(history_path),
        "qa_loop_history_sha256": _file_sha256(history_path),
    }

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

    # Tier 0 — Preconditions/freshness.  This is intentionally about whether
    # downstream evaluators are looking at the current manuscript, not about the
    # paper's scholarly content.
    tier0_failing: list[str] = []
    artifact_checks: dict[str, Any] = {}
    paper_exists = bool(state.artifacts.paper_full_tex and Path(state.artifacts.paper_full_tex).exists())
    artifact_checks["paper_full_tex"] = {"status": "pass" if paper_exists else "fail", "path": state.artifacts.paper_full_tex}
    if not paper_exists:
        tier0_failing.append("paper_full_tex_missing")
    artifact_checks["manuscript_hash"] = {"status": "pass" if manuscript_hash else "fail", "sha256": manuscript_hash}
    if not manuscript_hash:
        tier0_failing.append("manuscript_hash_missing")
    stale_or_missing = _strict_issue_codes(
        reproducibility,
        kinds={"validation_report_missing", "validation_report_stale", "figure_placement_review_missing", "figure_placement_review_stale"},
    )
    planning_status = planning_artifact_status(cwd)
    planning_freshness_codes = list(planning_status.get("failing_codes") or [])
    artifact_checks["freshness"] = {
        "status": "pass" if not (stale_or_missing or planning_freshness_codes) else "fail",
        "stale_against_manuscript_hash": stale_or_missing,
        "planning_artifact_issues": planning_freshness_codes,
    }
    tier0_failing.extend(stale_or_missing)
    if paper_exists:
        tier0_failing.extend(planning_freshness_codes)
    tier0 = _tier(
        status=_status_from_failures(tier0_failing),
        checks={
            "artifacts_present": artifact_checks["paper_full_tex"],
            "manuscript_hash": artifact_checks["manuscript_hash"],
            "freshness": artifact_checks["freshness"],
            "planning_artifacts": {
                "status": planning_status.get("status"),
                "failing_codes": planning_freshness_codes,
                "artifacts": planning_status.get("artifacts"),
            },
        },
        failing_codes=tier0_failing,
    )

    tiers: dict[str, Any] = {"tier_0_preconditions": tier0}
    leakage = _manuscript_prompt_leakage(state)
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
        provenance_complete = int(reproducibility.get("prompt_trace_file_count") or 0) > 0
        tier1 = _tier(
            status=_status_from_failures(tier1_failing),
            checks={
                "compile_clean": compile_check,
                "citation_key_integrity": {"status": "pass" if not citation_issues else "fail", "issues": citation_issues},
                "prompt_meta_leakage": {"status": "pass" if not leakage else "fail", "markers": leakage},
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
            source_material = _source_material_fidelity_check(state)
            source_obligations = evaluate_source_obligations(cwd)
            high_risk_claims = _high_risk_claim_sweep(state, source_obligations)
            planning_satisfaction = _planning_satisfaction_check(state, planning_status)
            tier2_failing: list[str] = []
            for code in sorted(TIER2_CLAIM_CODES):
                if claim_counts.get(code, 0) > 0:
                    tier2_failing.append(code)
            tier2_failing.extend(citation_support.get("failing_codes") or [])
            tier2_failing.extend(citation_integrity.get("failing_codes") or [])
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
            "ralph_handoff": ralph_evidence["ralph_handoff"],
            "ralph_handoff_sha256": ralph_evidence["ralph_handoff_sha256"],
            "qa_loop_history": ralph_evidence["qa_loop_history"],
            "qa_loop_history_sha256": ralph_evidence["qa_loop_history_sha256"],
            "omx_evidence_summary": str(artifact_path(cwd, OMX_EVIDENCE_SUMMARY_FILENAME)),
            "omx_evidence_summary_sha256": _file_sha256(artifact_path(cwd, OMX_EVIDENCE_SUMMARY_FILENAME)),
            "omx_review_handoff": str(artifact_path(cwd, OMX_REVIEW_HANDOFF_FILENAME)),
            "omx_review_handoff_sha256": _file_sha256(artifact_path(cwd, OMX_REVIEW_HANDOFF_FILENAME)),
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












def build_quality_loop_plan(
    cwd: str | Path | None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    accept_mixed_provenance: bool = False,
    quality_eval: dict[str, Any] | None = None,
    quality_eval_path: str | Path | None = None,
) -> dict[str, Any]:
    state = load_session(cwd)
    reproducibility = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    fidelity = run_fidelity_audit(cwd)
    quality_eval = quality_eval or build_quality_eval(
        cwd,
        quality_mode=quality_mode,
        require_live_verification=require_live_verification,
        max_iterations=max_iterations,
        reproducibility=reproducibility,
        fidelity=fidelity,
    )
    citation_support_review_path = _citation_support_path(cwd, state)
    citation_review_expected_sha256 = (
        (quality_eval.get("source_artifacts") or {}).get("citation_review_sha256")
        if isinstance(quality_eval.get("source_artifacts"), dict)
        else None
    )
    citation_review_current_sha256 = _file_sha256(citation_support_review_path)
    if citation_review_expected_sha256 and citation_review_current_sha256:
        citation_review_identity_status = (
            "pass" if citation_review_expected_sha256 == citation_review_current_sha256 else "stale_or_divergent"
        )
    elif citation_review_expected_sha256 or citation_review_current_sha256:
        citation_review_identity_status = "missing_expected_or_current"
    else:
        citation_review_identity_status = "missing"
    quality_eval_for_plan = dict(quality_eval)
    quality_eval_for_plan["source_artifacts"] = {
        **(quality_eval.get("source_artifacts") if isinstance(quality_eval.get("source_artifacts"), dict) else {}),
        "citation_review_current_sha256": citation_review_current_sha256,
        "citation_review_identity_status": citation_review_identity_status,
    }
    provenance_for_plan = dict(quality_eval.get("provenance_trust") if isinstance(quality_eval.get("provenance_trust"), dict) else {})
    if provenance_for_plan.get("level") == "mixed" and accept_mixed_provenance:
        provenance_for_plan["mixed_acceptance"] = _mixed_provenance_acceptance(cwd, quality_eval)
    quality_eval_for_plan["provenance_trust"] = provenance_for_plan

    detailed_actions = (
        _citation_actions(reproducibility)
        + _validation_actions(reproducibility)
        + _figure_review_actions(state)
        + _generated_placeholder_figure_actions(state)
        + _mode_actions(reproducibility)
        + _warning_actions(reproducibility)
        + _fidelity_actions(fidelity)
        + _quality_eval_actions(quality_eval_for_plan)
    )
    if citation_review_identity_status != "pass":
        detailed_actions.append(
            _action(
                action_id="quality-eval:citation-support-identity",
                code="citation_support_review_stale",
                source=str(citation_support_review_path),
                target="claim safety",
                automation="automatic",
                reason="Citation-support review identity is missing, stale, or divergent from the quality-eval snapshot.",
                suggested_commands=["paperorchestra review-citations --evidence-mode web", "paperorchestra qa-loop-plan --quality-mode claim_safe"],
                ralph_instruction="Regenerate citation-support review and quality-eval before treating the QA loop plan as ready.",
            )
        )
    detailed_codes = {str(action.get("code")) for action in detailed_actions}
    strict_fallback_actions = [
        action for action in _strict_content_actions(reproducibility) if str(action.get("code")) not in detailed_codes
    ]
    actions = _dedupe_actions(detailed_actions + strict_fallback_actions)

    automatic = [action for action in actions if action.get("automation") == "automatic"]
    semi_auto = [action for action in actions if action.get("automation") == "semi_auto"]
    human_needed = [action for action in actions if action.get("automation") == "human_needed"]
    verdict, verdict_rationale = _plan_verdict(
        quality_eval_for_plan,
        actions,
        accept_mixed_provenance=accept_mixed_provenance,
    )
    operator_packet_path = artifact_path(cwd, "operator_review_packet.json")
    operator_packet_sha = None
    if operator_packet_path.exists():
        try:
            packet_payload = read_json(operator_packet_path)
            if isinstance(packet_payload, dict):
                operator_packet_sha = packet_payload.get("packet_sha256")
        except Exception:
            operator_packet_sha = None
    supervised_handoff = None
    if verdict == "human_needed":
        owner_categories = sorted(
            {
                "proof" if "proof" in str(action.get("code") or "").lower() or "security" in str(action.get("code") or "").lower()
                else "bibliography" if "citation" in str(action.get("code") or "").lower() or "reference" in str(action.get("code") or "").lower()
                else "experiment" if "benchmark" in str(action.get("code") or "").lower() or "experiment" in str(action.get("code") or "").lower()
                else "implementation" if "compile" in str(action.get("code") or "").lower() or "validation" in str(action.get("code") or "").lower()
                else "author"
                for action in human_needed
            }
        )
        supervised_handoff = {
            "schema_version": "supervised-handoff/1",
            "operator_feedback_entry": {
                "kind": "metadata_only",
                "source": "codex_operator",
                "not_independent_human_review": True,
                "allowed_entrypoints": [
                    "build-operator-review-packet",
                    "import-operator-feedback",
                    "apply-operator-feedback",
                ],
                "packet_path": str(operator_packet_path) if operator_packet_sha else None,
                "packet_sha256": operator_packet_sha,
            },
            "supervised_budget": {
                "event_type": "operator_feedback_cycle",
                "separate_from_automatic_budget": True,
            },
            "actionable_failure_summary": {
                "owner_categories": owner_categories,
            },
        }

    plan_payload = {
        "schema_version": QA_LOOP_PLAN_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": state.session_id,
        "reads": _plan_reads(quality_eval_path, quality_eval_for_plan),
        "verdict": verdict,
        "verdict_rationale": verdict_rationale,
        "quality_eval_summary": _quality_eval_summary_for_plan(quality_eval_for_plan),
        "next_iteration_target_hash": None,
        "summary": {
            "action_count": len(actions),
            "automatic_count": len(automatic),
            "semi_auto_count": len(semi_auto),
            "human_needed_count": len(human_needed),
            "manual_count": len(human_needed),  # backwards-readable alias for older operators
            "reproducibility_verdict": reproducibility.get("verdict"),
            "fidelity_status": fidelity.get("overall_status"),
        },
        "stop_conditions": {
            "ready_for_human_finalization": "Tier 0, 1, and 2 pass; Tier 3 scorecard passes without anti-inflation; provenance is live or explicitly accepted mixed; Tier 4 remains human-owned.",
            "continue": "automatic or semi-automatic repair actions remain and the loop still has iteration budget.",
            "human_needed": "remaining actions require HITL/domain judgment, critic disagreement resolution, provenance acceptance, or Tier 4 ownership.",
            "failed": "budget is exhausted, repeated hard-gate failures show no progress, non-reviewable structural artifacts such as prompt/meta leakage are present, or oscillation/regression makes autonomous continuation unsafe.",
        },
        "source_artifacts": {
            "paper_full_tex": state.artifacts.paper_full_tex,
            "compiled_pdf": state.artifacts.compiled_pdf,
            "reproducibility_audit": state.artifacts.latest_reproducibility_json,
            "fidelity_audit": state.artifacts.latest_fidelity_json,
            "figure_placement_review": state.artifacts.latest_figure_placement_review_json,
            "latest_validation": state.artifacts.latest_validation_json,
            "latest_section_review": getattr(state.artifacts, "latest_section_review_json", None),
            "citation_support_review": str(citation_support_review_path),
            "narrative_plan": state.artifacts.narrative_plan_json,
            "claim_map": state.artifacts.claim_map_json,
            "citation_placement_plan": state.artifacts.citation_placement_plan_json,
            "source_obligations": str(source_obligations_path(cwd)),
            "quality_eval": str(quality_eval_path) if quality_eval_path else None,
            "operator_review_packet": str(operator_packet_path) if operator_packet_sha else None,
            "citation_review_sha256": citation_review_expected_sha256,
            "citation_review_current_sha256": citation_review_current_sha256,
            "citation_review_identity_status": citation_review_identity_status,
        },
        "mixed_provenance_acceptance": provenance_for_plan.get("mixed_acceptance"),
        "audit_snapshots": {
            "reproducibility": reproducibility,
            "fidelity": fidelity,
        },
        "blocking_reasons": reproducibility.get("blocking_reasons", []),
        "warning_reasons": reproducibility.get("warning_reasons", []),
        "repair_actions": actions,
        "human_handoff": _human_handoff(verdict, actions, quality_eval),
        "next_ralph_instruction": _next_ralph_instruction(verdict, actions),
    }
    if supervised_handoff is not None:
        plan_payload["supervised_handoff"] = supervised_handoff
    return plan_payload






def append_quality_loop_history(
    cwd: str | Path | None,
    quality_eval: dict[str, Any],
    *,
    verdict: str | None = None,
    plan_path: str | Path | None = None,
    quality_eval_path: str | Path | None = None,
    event_type: str = "quality_eval",
    consumes_budget: bool | None = None,
    execution_path: str | Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    path = quality_loop_history_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    if consumes_budget is None:
        consumes_budget = event_type in BUDGET_CONSUMING_HISTORY_EVENTS
    entry = {
        "recorded_at": utc_now_iso(),
        "event_type": event_type,
        "consumes_budget": bool(consumes_budget),
        "session_id": quality_eval.get("session_id"),
        "mode": quality_eval.get("mode"),
        "manuscript_hash": quality_eval.get("manuscript_hash"),
        "quality_eval_path": str(quality_eval_path) if quality_eval_path else None,
        "plan_path": str(plan_path) if plan_path else None,
        "execution_path": str(execution_path) if execution_path else None,
        "quality_eval_sha256": f"sha256:{_file_sha256(quality_eval_path)}" if quality_eval_path else f"sha256:{_sha256_jsonable(quality_eval)}",
        "plan_sha256": f"sha256:{_file_sha256(plan_path)}" if plan_path else None,
        "verdict": verdict,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "tier_statuses": _tier_statuses(quality_eval),
        "tier_3_overall_score": ((quality_eval.get("tiers") or {}).get("tier_3_scholarly_quality") or {}).get("overall_score") if isinstance(quality_eval.get("tiers"), dict) else None,
        "tier_3_axis_scores": ((quality_eval.get("tiers") or {}).get("tier_3_scholarly_quality") or {}).get("axis_scores") if isinstance(quality_eval.get("tiers"), dict) else {},
    }
    if extra:
        entry.update(extra)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def write_quality_eval(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    append_history: bool = False,
    current_attempt_consumes_budget: bool = False,
) -> tuple[Path, dict[str, Any]]:
    fidelity_payload = run_fidelity_audit(cwd)
    fidelity_path = artifact_path(cwd, "fidelity.audit.json")
    write_json(fidelity_path, fidelity_payload)
    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(fidelity_path)
    save_session(cwd, state)
    write_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    reproducibility_payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    payload = build_quality_eval(
        cwd,
        quality_mode=quality_mode,
        require_live_verification=require_live_verification,
        max_iterations=max_iterations,
        reproducibility=reproducibility_payload,
        fidelity=fidelity_payload,
        current_attempt_consumes_budget=current_attempt_consumes_budget,
    )
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "quality-eval.json")
    write_json(path, payload)
    state = load_session(cwd)
    state.notes.append(f"Quality eval recorded: {path.name}")
    save_session(cwd, state)
    if append_history:
        append_quality_loop_history(cwd, payload, quality_eval_path=path, event_type="quality_eval", consumes_budget=False)
    return path, payload


def _validate_quality_eval_input(
    quality_eval: dict[str, Any],
    *,
    state,
    reproducibility: dict[str, Any],
    fidelity: dict[str, Any],
    quality_eval_path: Path,
) -> None:
    current_hash = _file_sha256(state.artifacts.paper_full_tex)
    expected_manuscript_hash = f"sha256:{current_hash}" if current_hash else None
    if quality_eval.get("manuscript_hash") != expected_manuscript_hash:
        raise ValueError(
            "quality-eval input is stale for the current manuscript: "
            f"{quality_eval_path} has {quality_eval.get('manuscript_hash')!r}, expected {expected_manuscript_hash!r}"
        )
    snapshot_hashes = quality_eval.get("audit_snapshot_hashes")
    if isinstance(snapshot_hashes, dict):
        expected_repro = f"sha256:{_sha256_jsonable(reproducibility)}"
        expected_fidelity = f"sha256:{_sha256_jsonable(fidelity)}"
        if snapshot_hashes.get("reproducibility") != expected_repro:
            raise ValueError(f"quality-eval input is stale for the current reproducibility audit: {quality_eval_path}")
        if snapshot_hashes.get("fidelity") != expected_fidelity:
            raise ValueError(f"quality-eval input is stale for the current fidelity audit: {quality_eval_path}")


def write_quality_loop_plan(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
    quality_mode: str = "ralph",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    accept_mixed_provenance: bool = False,
    quality_eval_input_path: str | Path | None = None,
    append_history: bool = True,
) -> tuple[Path, dict[str, Any]]:
    fidelity_payload = run_fidelity_audit(cwd)
    fidelity_path = artifact_path(cwd, "fidelity.audit.json")
    write_json(fidelity_path, fidelity_payload)
    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(fidelity_path)
    save_session(cwd, state)
    write_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    reproducibility_payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    if quality_eval_input_path:
        quality_eval_path = Path(quality_eval_input_path).resolve()
        loaded_quality_eval = read_json(quality_eval_path)
        if not isinstance(loaded_quality_eval, dict):
            raise ValueError(f"quality-eval input is not a JSON object: {quality_eval_path}")
        state_for_eval = load_session(cwd)
        _validate_quality_eval_input(
            loaded_quality_eval,
            state=state_for_eval,
            reproducibility=reproducibility_payload,
            fidelity=fidelity_payload,
            quality_eval_path=quality_eval_path,
        )
        quality_eval = loaded_quality_eval
    else:
        quality_eval = build_quality_eval(
            cwd,
            quality_mode=quality_mode,
            require_live_verification=require_live_verification,
            max_iterations=max_iterations,
            reproducibility=reproducibility_payload,
            fidelity=fidelity_payload,
        )
        quality_eval_path = artifact_path(cwd, "quality-eval.json")
        write_json(quality_eval_path, quality_eval)
    payload = build_quality_loop_plan(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval=quality_eval,
        quality_eval_path=quality_eval_path,
    )
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "qa-loop.plan.json")
    write_json(path, payload)
    if append_history:
        append_quality_loop_history(
            cwd,
            quality_eval,
            verdict=payload.get("verdict"),
            plan_path=path,
            quality_eval_path=quality_eval_path,
            event_type="qa_loop_plan",
            consumes_budget=False,
        )
    state = load_session(cwd)
    state.notes.append(f"QA loop plan recorded: {path.name}")
    save_session(cwd, state)
    return path, payload
