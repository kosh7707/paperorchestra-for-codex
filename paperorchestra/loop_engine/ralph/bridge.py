from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.core.io import extract_latex
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.errors import ContractError
from paperorchestra.engine.completion import (
    _build_completion_request,
    _complete_with_runtime_mode,
)
from paperorchestra.engine.pipeline import (
    compile_current_paper,
    plan_narrative_and_claims,
    refine_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.runtime.providers import BaseProvider, get_citation_support_provider
from paperorchestra.manuscript.source_obligations import write_source_obligations
from ..quality.loop import (
    CITATION_SUPPORT_REVIEW_REFRESH_CODES,
    DEFAULT_MAX_ITERATIONS,
    QA_LOOP_SUPPORTED_HANDLER_CODES,
    REVIEW_REFRESH_CODES,
    append_quality_loop_history,
    build_quality_loop_plan,
    write_quality_eval,
    write_quality_loop_plan,
)
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.validator import extract_citation_keys
from .handoff import (
    build_qa_loop_brief,
    build_ralph_start_payload,
    launch_omx_ralph,
    write_qa_loop_brief,
)
from .inputs import (
    _load_explicit_qa_loop_plan,
    _load_explicit_quality_eval,
    _quality_eval_path_from_plan,
    _stage_explicit_citation_support_review,
    _validate_plan_quality_eval_identity,
)
from .artifacts import (
    _refresh_citation_integrity_for_current_manuscript,
    _try_rebuild_bib_for_citation_quality,
    _write_execution_artifact,
)
from .semantic_recheck import _citation_repair_failure_payload
from .repair import (
    _non_supported_citation_items,
    _repair_prompt,
    repair_citation_claims,
)
from .state import (
    EXIT_CODES,
    NON_SUPPORTED_CITATION_STATUSES,
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_BRIEF_FILENAME,
    QA_LOOP_EXECUTION_SCHEMA_VERSION,
    QA_LOOP_HANDOFF_FILENAME,
    SUPPORTED_HANDLER_CODES,
    TERMINAL_VERDICTS,
    StepResult,
    _artifact_sha,
    atomic_write_text,
    _citation_issue_count,
    _citation_summary,
    _file_content_snapshot,
    _failing_codes,
    _next_execution_path,
    _plan_path,
    _qa_loop_step_command,
    _read_json,
    _restore_file_content_snapshot,
    _restore_session_mutation_snapshot,
    _session_mutation_snapshot,
    clear_pending_manuscript_write,
    compute_progress_delta,
    guarded_replace_manuscript_text,
    qa_loop_exit_code,
    quality_eval_status,
    recover_pending_manuscript_write,
)


def _restore_current_after_uncommitted_candidate(
    cwd: str | Path | None,
    *,
    paper_path: Path | None,
    original_paper: str | None,
    mutation_snapshot: dict[str, Any],
    citation_review_snapshot: dict[str, Any],
    citation_trace_snapshot: dict[str, Any],
    require_compile: bool,
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    accept_mixed_provenance: bool,
    before_eval: dict[str, Any],
    before_summary: dict[str, int],
    actions_attempted: bool,
    validation_name: str,
) -> dict[str, Any] | None:
    if paper_path is None or original_paper is None:
        return None
    atomic_write_text(paper_path, original_paper)
    clear_pending_manuscript_write(cwd, status="restored", reason="uncommitted_candidate_restored")
    _restore_session_mutation_snapshot(cwd, mutation_snapshot)
    _restore_file_content_snapshot(citation_review_snapshot)
    _restore_file_content_snapshot(citation_trace_snapshot)
    restored_validation_path, restored_validation_payload = record_current_validation_report(cwd, name=validation_name)
    restored_compile_payload: dict[str, Any] | None = None
    if require_compile:
        try:
            restored_pdf_path = compile_current_paper(cwd)
            restored_compile_payload = {"ok": True, "pdf": str(restored_pdf_path)}
        except Exception as exc:
            restored_compile_payload = {"ok": False, "error": str(exc)}
    restored_figure_path, restored_figure_payload = write_figure_placement_review(cwd)
    refreshed_citation_integrity = _refresh_citation_integrity_for_current_manuscript(
        cwd,
        quality_mode=quality_mode,
    )
    final_eval_path, final_eval = write_quality_eval(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        current_attempt_consumes_budget=actions_attempted,
    )
    final_plan_path, final_plan = write_quality_loop_plan(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=final_eval_path,
    )
    final_summary = _citation_summary(cwd)
    final_progress = compute_progress_delta(before_eval, final_eval, before_summary, final_summary)
    return {
        "verification": {
            "validate_current": {"path": str(restored_validation_path), "ok": restored_validation_payload.get("ok")},
            "compile": restored_compile_payload,
            "figure_placement_review": {
                "path": str(restored_figure_path),
                "manuscript_sha256": restored_figure_payload.get("manuscript_sha256")
                if isinstance(restored_figure_payload, dict)
                else None,
            },
            "citation_integrity": refreshed_citation_integrity,
            "quality_eval": {"path": str(final_eval_path)},
            "qa_loop_plan": {"path": str(final_plan_path)},
            "citation_support_review_restored": {"path": citation_review_snapshot.get("path"), "restored": True},
            "citation_support_trace_restored": {"path": citation_trace_snapshot.get("path"), "restored": True},
        },
        "quality_eval_path": final_eval_path,
        "quality_eval": final_eval,
        "qa_loop_plan_path": final_plan_path,
        "qa_loop_plan": final_plan,
        "citation_summary": final_summary,
        "progress": final_progress,
    }


def _executable_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    actions = plan.get("repair_actions") if isinstance(plan, dict) else []
    return [
        action
        for action in actions
        if isinstance(action, dict)
        and action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) in SUPPORTED_HANDLER_CODES
    ]


def _unsupported_executable_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    actions = plan.get("repair_actions") if isinstance(plan, dict) else []
    return [
        action
        for action in actions
        if isinstance(action, dict)
        and action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) not in SUPPORTED_HANDLER_CODES
    ]


def _preserve_citation_candidate_for_approval(cwd: str | Path | None, candidate_path: str | Path | None) -> str | None:
    if not candidate_path:
        return None
    source = Path(candidate_path).resolve()
    if not source.exists() or not source.is_file():
        return str(source)
    digest = _artifact_sha(source)
    if not digest:
        return str(source)
    short = digest.split(":", 1)[-1][:16]
    preserved = artifact_path(cwd, f"paper.citation-repair.approval-{short}.candidate.tex")
    if not preserved.exists() or _artifact_sha(preserved) != digest:
        preserved.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return str(preserved)


def _qa_loop_int_metric(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _qa_loop_tier2_metric_counts(quality_eval: dict[str, Any] | None) -> dict[str, int]:
    """Return generic Tier-2 issue counts for candidate auto-commit guards."""

    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers, dict) else {}
    checks = tier2.get("checks") if isinstance(tier2, dict) else {}
    metrics: dict[str, int] = {}
    support = checks.get("citation_support_critic") if isinstance(checks, dict) else None
    if isinstance(support, dict):
        summary = support.get("canonical_summary") or support.get("summary") or {}
        for code, count_field, summary_field in [
            ("citation_support_unsupported", "unsupported_count", "unsupported"),
            ("citation_support_contradicted", "contradicted_count", "contradicted"),
            ("citation_support_weak", "weakly_supported_count", "weakly_supported"),
            ("citation_support_manual_check", "needs_manual_check_count", "needs_manual_check"),
            ("citation_support_metadata_only", "metadata_only_count", "metadata_only"),
            ("citation_support_insufficient_evidence", "insufficient_evidence_count", "insufficient_evidence"),
            ("citation_support_evidence_missing", "evidence_missing_count", "evidence_missing"),
        ]:
            value = _qa_loop_int_metric(support.get(count_field))
            if value is None and isinstance(summary, dict):
                value = _qa_loop_int_metric(summary.get(summary_field))
            if value is not None:
                metrics[code] = value
    citation_quality = checks.get("citation_quality_gate") if isinstance(checks, dict) else None
    if isinstance(citation_quality, dict):
        counts = citation_quality.get("counts") if isinstance(citation_quality.get("counts"), dict) else {}
        for code, field in [
            ("citation_duplicate_support", "duplicate_reference_count"),
            ("citation_bomb_detected", "citation_bomb_count"),
            ("critical_citation_support_missing", "critical_need_count"),
            ("critical_unsupported_citation", "critical_unsupported_count"),
        ]:
            value = _qa_loop_int_metric(counts.get(field))
            if value is not None:
                metrics.setdefault(code, value)
    high_risk = checks.get("high_risk_claim_sweep") if isinstance(checks, dict) else None
    if isinstance(high_risk, dict):
        value = _qa_loop_int_metric(high_risk.get("item_count"))
        if value is None and isinstance(high_risk.get("items"), list):
            value = len(high_risk["items"])
        if value is not None:
            metrics["high_risk_uncited_claim"] = value
    return metrics


def _active_metric_regressions(
    before_quality_eval: dict[str, Any] | None,
    after_quality_eval: dict[str, Any] | None,
    *,
    active_codes: list[str],
) -> list[dict[str, int | str]]:
    before_metrics = _qa_loop_tier2_metric_counts(before_quality_eval)
    after_metrics = _qa_loop_tier2_metric_counts(after_quality_eval)
    regressions: list[dict[str, int | str]] = []
    for code in sorted(dict.fromkeys(str(item) for item in active_codes if str(item).strip())):
        before = before_metrics.get(code)
        after = after_metrics.get(code)
        if before is not None and after is not None and after > before:
            regressions.append({"code": code, "before": before, "after": after, "delta": after - before})
    return regressions


def _auto_commit_progressive_citation_candidate(
    *,
    progress: dict[str, Any],
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    require_compile: bool,
    before_quality_eval: dict[str, Any] | None,
    after_quality_eval: dict[str, Any] | None,
    after_codes: set[str],
    residual_citation_failures: list[str],
) -> tuple[bool, str]:
    """Return whether a verified citation-repair candidate can stay canonical.

    The QA loop should not spend scarce human/operator cycles merely to accept a
    candidate that has already passed validation/compile and strictly improves
    the active Tier-2 citation metrics.  Keeping such a candidate lets the next
    automatic QA iteration continue from the better manuscript while final
    readiness remains gated by Tier-2 passing.  Pre-existing non-worsened Tier-2
    blockers such as duplicate-support findings may remain for later executable
    handlers, but the candidate must not add new failures, regress active
    metrics, or leave non-human-reviewable citation-support failures.
    """

    if validation_payload.get("ok") is not True:
        return False, "validation_failed"
    if require_compile and (not isinstance(compile_payload, dict) or compile_payload.get("ok") is not True):
        return False, "compile_failed"
    if progress.get("forward_progress") is not True:
        return False, "no_forward_progress"
    if progress.get("new_codes"):
        return False, "new_failure_codes"
    after_statuses = quality_eval_status(after_quality_eval or {})
    if after_statuses.get("tier_0_preconditions") == "fail":
        return False, "tier0_failed"
    if after_statuses.get("tier_1_structural") == "fail":
        return False, "tier1_failed"
    regressions = _active_metric_regressions(
        before_quality_eval,
        after_quality_eval,
        active_codes=[str(code) for code in progress.get("before_failing_codes") or []],
    )
    if regressions:
        return False, "active_tier2_metric_regression"
    non_human_reviewable_residuals = sorted(
        code
        for code in residual_citation_failures
        if code not in {"citation_support_manual_check", "citation_support_weak"}
    )
    if non_human_reviewable_residuals:
        return False, "non_human_reviewable_citation_support_residuals"
    return True, "strict_progress_without_new_failures"


def run_qa_loop_step(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    require_compile: bool = False,
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
    quality_eval_input_path: str | Path | None = None,
    qa_loop_plan_input_path: str | Path | None = None,
    citation_support_review_path: str | Path | None = None,
) -> StepResult:
    recover_pending_manuscript_write(cwd)
    started = utc_now_iso()
    explicit_citation_support_path = _stage_explicit_citation_support_review(cwd, citation_support_review_path)
    if qa_loop_plan_input_path:
        before_plan_path = Path(qa_loop_plan_input_path).resolve()
        before_plan = _load_explicit_qa_loop_plan(cwd, before_plan_path)
        quality_eval_input_path = quality_eval_input_path or _quality_eval_path_from_plan(before_plan)
        if not quality_eval_input_path:
            raise ValueError(f"qa-loop-plan input does not identify a quality-eval artifact: {before_plan_path}")
        before_eval_path, before_eval = _load_explicit_quality_eval(cwd, quality_eval_input_path)
        _validate_plan_quality_eval_identity(before_plan, before_eval_path)
    else:
        if quality_eval_input_path:
            before_eval_path, before_eval = _load_explicit_quality_eval(cwd, quality_eval_input_path)
        else:
            before_eval_path, before_eval = write_quality_eval(
                cwd,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
            )
        before_plan_path, before_plan = write_quality_loop_plan(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            quality_eval_input_path=before_eval_path,
        )
    before_summary = _citation_summary(cwd)
    initial_verdict = str(before_plan.get("verdict"))
    execution: dict[str, Any] = {
        "schema_version": QA_LOOP_EXECUTION_SCHEMA_VERSION,
        "started_at": started,
        "_reserved_execution_path": str(_next_execution_path(cwd)[1]),
        "input_quality_eval": str(before_eval_path),
        "input_plan": str(before_plan_path),
        "input_citation_support_review": str(explicit_citation_support_path) if explicit_citation_support_path else None,
        "input_artifacts": {
            "quality_eval": str(before_eval_path),
            "qa_loop_plan": str(before_plan_path),
            "citation_support_review": str(explicit_citation_support_path) if explicit_citation_support_path else None,
        },
        "actions_attempted": [],
        "actions_skipped": [],
        "before": {"failing_codes": _failing_codes(before_eval), "citation_support_summary": before_summary},
    }
    actions = _executable_actions(before_plan)
    if initial_verdict in TERMINAL_VERDICTS:
        execution.update({"completed_at": utc_now_iso(), "verdict": initial_verdict, "terminal_noop": True})
        path = _write_execution_artifact(cwd, execution)
        return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code(initial_verdict))
    unsupported_actions = _unsupported_executable_actions(before_plan)
    for action in unsupported_actions:
        execution["actions_skipped"].append({"code": action.get("code"), "reason": "unsupported_handler"})

    if not actions:
        execution.update({"completed_at": utc_now_iso(), "verdict": "human_needed", "reason": "no_supported_executable_handlers"})
        path = _write_execution_artifact(cwd, execution)
        return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code("human_needed"))

    state_for_rollback = load_session(cwd)
    paper_path = Path(state_for_rollback.artifacts.paper_full_tex) if state_for_rollback.artifacts.paper_full_tex else None
    original_paper = paper_path.read_text(encoding="utf-8") if paper_path and paper_path.exists() else None
    mutation_snapshot = _session_mutation_snapshot(state_for_rollback)
    citation_review_snapshot = _file_content_snapshot(paper_path.resolve().parent / "citation_support_review.json" if paper_path else None)
    citation_trace_snapshot = _file_content_snapshot(
        paper_path.resolve().parent / "citation_support_review.trace.json" if paper_path else None
    )
    citation_provider = get_citation_support_provider(
        citation_provider_name or ("shell" if citation_evidence_mode in {"web", "model"} else "mock"),
        command=citation_provider_command,
        evidence_mode=citation_evidence_mode,
    )
    citation_candidate_applied = False
    citation_candidate_path: str | None = None
    for action in actions:
        code = str(action.get("code"))
        if code in {
            "narrative_plan_missing",
            "claim_map_missing",
            "citation_placement_plan_missing",
            "narrative_plan_stale",
            "claim_map_stale",
            "citation_placement_plan_stale",
        }:
            paths = plan_narrative_and_claims(cwd, provider=None, runtime_mode=runtime_mode)
            execution["actions_attempted"].append(
                {
                    "code": code,
                    "handler": "plan_narrative",
                    "paths": {key: str(path) for key, path in paths.items()},
                }
            )
        elif code in {"validation_report_missing", "validation_report_stale"}:
            validation_path, validation_payload = record_current_validation_report(
                cwd,
                name="validation.qa-loop-step.precondition.json",
            )
            execution["actions_attempted"].append(
                {
                    "code": code,
                    "handler": "validate_current",
                    "path": str(validation_path),
                    "ok": validation_payload.get("ok"),
                }
            )
        elif code in {"figure_placement_review_missing", "figure_placement_review_stale"}:
            figure_path, figure_payload = write_figure_placement_review(cwd)
            execution["actions_attempted"].append(
                {
                    "code": code,
                    "handler": "review_figure_placement",
                    "path": str(figure_path),
                    "warning_count": (figure_payload.get("summary") or {}).get("warning_count")
                    if isinstance(figure_payload, dict)
                    else None,
                }
            )
        elif code in CITATION_SUPPORT_REVIEW_REFRESH_CODES | {"citation_support_evidence_research_needed"}:
            review_path = write_citation_support_review(cwd, provider=citation_provider, evidence_mode=citation_evidence_mode)
            execution["actions_attempted"].append({"code": code, "handler": "critique_citations", "path": str(review_path)})
        elif code in {
            "critical_unknown_reference",
            "critical_missing_bib_entry",
            "critical_unsupported_citation",
            "critical_citation_support_missing",
            "critical_weak_reference_identity",
        }:
            bibtex_rebuild = _try_rebuild_bib_for_citation_quality(cwd) if code == "critical_weak_reference_identity" else None
            review_path = write_citation_support_review(cwd, provider=citation_provider, evidence_mode=citation_evidence_mode)
            refreshed = _refresh_citation_integrity_for_current_manuscript(cwd, quality_mode=quality_mode)
            attempted = {
                "code": code,
                "handler": "refresh_citation_quality",
                "citation_support_review": str(review_path),
                "citation_integrity": refreshed,
            }
            if bibtex_rebuild is not None:
                attempted["bibtex_rebuild"] = bibtex_rebuild
            execution["actions_attempted"].append(attempted)
        elif code in {
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
        }:
            refreshed = _refresh_citation_integrity_for_current_manuscript(cwd, quality_mode=quality_mode)
            execution["actions_attempted"].append(
                {"code": code, "handler": "refresh_citation_integrity", "artifacts": refreshed}
            )
        elif code in REVIEW_REFRESH_CODES:
            path = review_current_paper(cwd, provider, runtime_mode=runtime_mode)
            execution["actions_attempted"].append({"code": code, "handler": "review", "path": str(path)})
        elif code in {
            "compile_report_missing",
            "compile_report_stale",
            "compile_report_legacy_untrusted",
            "compile_pdf_missing",
            "compile_pdf_stale",
            "compile_not_clean",
        }:
            try:
                pdf_path = compile_current_paper(cwd)
                execution["actions_attempted"].append({"code": code, "handler": "compile", "pdf": str(pdf_path), "ok": True})
            except Exception as exc:
                execution["actions_attempted"].append({"code": code, "handler": "compile", "ok": False, "error": str(exc)})
                break
        elif code in {"section_review_missing", "section_review_stale", "section_review_legacy_untrusted"}:
            path = write_section_review(cwd)
            execution["actions_attempted"].append({"code": code, "handler": "critique_sections", "path": str(path)})
        elif code in {"source_obligations_missing", "source_obligations_stale"}:
            path = write_source_obligations(cwd)
            execution["actions_attempted"].append({"code": code, "handler": "build_source_obligations", "path": str(path)})
        elif code in {"review_score_below_threshold", "section_quality_below_threshold", "source_material_coverage_insufficient"}:
            state = load_session(cwd)
            if not state.artifacts.latest_review_json:
                review_path = review_current_paper(cwd, provider, runtime_mode=runtime_mode)
                execution["actions_attempted"].append(
                    {"code": code, "handler": "review", "path": str(review_path), "reason": "required_before_refine"}
                )
            refine_result = refine_current_paper(
                cwd,
                provider,
                iterations=1,
                require_compile_for_accept=require_compile,
                runtime_mode=runtime_mode,
                claim_safe=quality_mode == "claim_safe",
            )
            section_path = write_section_review(cwd)
            execution["actions_attempted"].append(
                {"code": code, "handler": "refine", "result": refine_result, "section_review": str(section_path)}
            )
            if any(not item.get("accepted", False) for item in refine_result):
                break
        elif code in {
            "citation_support_critic_failed",
            "citation_density_policy_failed",
            "citation_coverage_insufficient",
            "high_risk_uncited_claim",
        }:
            repair = repair_citation_claims(cwd, provider, runtime_mode=runtime_mode, require_compile=require_compile, commit=False)
            if not repair.get("accepted"):
                failure = _citation_repair_failure_payload(code, repair)
                execution.setdefault("repair_failures", []).append(failure)
                execution["actionable_failure"] = {
                    "category": "citation_repair_failed",
                    "code": code,
                    "reason": failure["reason"],
                    "validation_failing_codes": failure["validation"]["failing_codes"],
                    "semantic_recheck_blockers": failure.get("semantic_recheck_blockers") or [],
                    "next_steps": failure["next_steps"],
                }
                execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
                break
            if paper_path and repair.get("candidate_path"):
                preserved_candidate_path = _preserve_citation_candidate_for_approval(cwd, repair.get("candidate_path"))
                if preserved_candidate_path:
                    repair = dict(repair)
                    repair.setdefault("raw_candidate_path", str(repair.get("candidate_path")))
                    repair["candidate_path"] = preserved_candidate_path
                    repair["candidate_sha256"] = _artifact_sha(preserved_candidate_path)
                citation_candidate_path = str(repair["candidate_path"])
                guarded_replace_manuscript_text(
                    cwd,
                    paper_path,
                    Path(citation_candidate_path).read_text(encoding="utf-8"),
                    reason="qa_loop_citation_candidate_for_validation",
                    original_text=original_paper,
                )
                citation_candidate_applied = True
            execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
        else:
            execution["actions_skipped"].append({"code": code, "reason": "no_handler"})

    try:
        validation_path, validation_payload = record_current_validation_report(cwd, name="validation.qa-loop-step.json")
        compile_payload: dict[str, Any] | None = None
        if require_compile:
            try:
                pdf_path = compile_current_paper(cwd)
                compile_payload = {"ok": True, "pdf": str(pdf_path)}
            except Exception as exc:
                compile_payload = {"ok": False, "error": str(exc)}
        section_review_path = write_section_review(cwd)
        figure_review_path, figure_review_payload = write_figure_placement_review(cwd)
        citation_review_path = write_citation_support_review(cwd, provider=citation_provider, evidence_mode=citation_evidence_mode)
        refreshed_citation_integrity = _refresh_citation_integrity_for_current_manuscript(
            cwd,
            quality_mode=quality_mode,
        )
        after_eval_path, after_eval = write_quality_eval(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            current_attempt_consumes_budget=bool(execution["actions_attempted"]),
        )
        after_plan_path, after_plan = write_quality_loop_plan(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            quality_eval_input_path=after_eval_path,
        )
        after_summary = _citation_summary(cwd)
        progress = compute_progress_delta(before_eval, after_eval, before_summary, after_summary)
        verdict = str(after_plan.get("verdict"))
        candidate_state: dict[str, Any] | None = None
        if citation_candidate_applied:
            candidate_state = {
                "manuscript_path": citation_candidate_path,
                "verification": {
                    "validate_current": {"path": str(validation_path), "ok": validation_payload.get("ok")},
                    "compile": compile_payload,
                    "section_review": {"path": str(section_review_path)},
                    "figure_placement_review": {
                        "path": str(figure_review_path),
                        "manuscript_sha256": figure_review_payload.get("manuscript_sha256")
                        if isinstance(figure_review_payload, dict)
                        else None,
                    },
                    "citation_support_review": {"path": str(citation_review_path)},
                    "citation_integrity": refreshed_citation_integrity,
                    "quality_eval": {"path": str(after_eval_path)},
                    "qa_loop_plan": {"path": str(after_plan_path)},
                },
                "after": {"failing_codes": _failing_codes(after_eval), "citation_support_summary": after_summary},
                "quality_eval_path": str(after_eval_path),
                "qa_loop_plan_path": str(after_plan_path),
                "qa_loop_plan_verdict": verdict,
                "progress": progress,
            }
        final_eval = after_eval
        final_plan = after_plan
        final_eval_path = after_eval_path
        final_plan_path = after_plan_path
        final_summary = after_summary
        final_progress = progress
        final_verification = {
            "validate_current": {"path": str(validation_path), "ok": validation_payload.get("ok")},
            "compile": compile_payload,
            "section_review": {"path": str(section_review_path)},
            "figure_placement_review": {
                "path": str(figure_review_path),
                "manuscript_sha256": figure_review_payload.get("manuscript_sha256")
                if isinstance(figure_review_payload, dict)
                else None,
            },
            "citation_support_review": {"path": str(citation_review_path)},
            "citation_integrity": refreshed_citation_integrity,
            "quality_eval": {"path": str(final_eval_path)},
            "qa_loop_plan": {"path": str(final_plan_path)},
        }
        after_codes = set(_failing_codes(after_eval))
        residual_citation_failures = sorted(code for code in after_codes if code.startswith("citation_support_"))
        auto_commit_allowed, auto_commit_reason = (
            _auto_commit_progressive_citation_candidate(
                progress=progress,
                validation_payload=validation_payload,
                compile_payload=compile_payload,
                require_compile=require_compile,
                before_quality_eval=before_eval,
                after_quality_eval=after_eval,
                after_codes=after_codes,
                residual_citation_failures=residual_citation_failures,
            )
            if citation_candidate_applied
            else (False, "no_citation_candidate")
        )
        if citation_candidate_applied and auto_commit_allowed:
            clear_pending_manuscript_write(
                cwd,
                status="resolved",
                reason="qa_loop_progressive_citation_candidate_committed",
            )
            execution["candidate_state"] = candidate_state
            execution["candidate_progress"] = progress
            execution["candidate_auto_commit"] = {
                "status": "committed_for_continued_qa",
                "reason": auto_commit_reason,
                "candidate_path": citation_candidate_path,
                "candidate_sha256": _artifact_sha(citation_candidate_path),
                "residual_citation_failures": residual_citation_failures,
                "after_failing_codes": sorted(after_codes),
            }
        elif citation_candidate_applied and any(code.startswith("citation_support_") for code in after_codes):
            restored = _restore_current_after_uncommitted_candidate(
                cwd,
                paper_path=paper_path,
                original_paper=original_paper,
                mutation_snapshot=mutation_snapshot,
                citation_review_snapshot=citation_review_snapshot,
                citation_trace_snapshot=citation_trace_snapshot,
                require_compile=require_compile,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                accept_mixed_provenance=accept_mixed_provenance,
                before_eval=before_eval,
                before_summary=before_summary,
                actions_attempted=bool(execution["actions_attempted"]),
                validation_name="validation.qa-loop-step.rollback.json",
            )
            if restored:
                final_eval_path = restored["quality_eval_path"]
                final_eval = restored["quality_eval"]
                final_plan_path = restored["qa_loop_plan_path"]
                final_plan = restored["qa_loop_plan"]
                final_summary = restored["citation_summary"]
                final_progress = restored["progress"]
                final_verification = restored["verification"]
                execution["restored_current_verification"] = restored["verification"]
                execution["restored_current_state"] = {
                    "verification": restored["verification"],
                    "after": {"failing_codes": _failing_codes(final_eval), "citation_support_summary": final_summary},
                    "quality_eval_path": str(final_eval_path),
                    "qa_loop_plan_path": str(final_plan_path),
                    "qa_loop_plan_verdict": str(final_plan.get("verdict")),
                    "progress": final_progress,
                }
            verdict = "human_needed"
            execution["candidate_rollback"] = {
                "reason": "citation_support_approval_failed",
                "failing_codes": residual_citation_failures,
                "auto_commit_blocked_reason": auto_commit_reason,
            }
            execution["candidate_state"] = candidate_state
            execution["candidate_progress"] = progress
            execution["candidate_handoff"] = {
                "status": "human_needed_candidate_rejected_by_citation_support",
                "reason": "semi_auto citation repair did not satisfy the auto-commit safety gate",
                "candidate_path": citation_candidate_path,
                "residual_citation_failures": residual_citation_failures,
                "auto_commit_blocked_reason": auto_commit_reason,
            }
        elif citation_candidate_applied:
            restored = _restore_current_after_uncommitted_candidate(
                cwd,
                paper_path=paper_path,
                original_paper=original_paper,
                mutation_snapshot=mutation_snapshot,
                citation_review_snapshot=citation_review_snapshot,
                citation_trace_snapshot=citation_trace_snapshot,
                require_compile=require_compile,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                accept_mixed_provenance=accept_mixed_provenance,
                before_eval=before_eval,
                before_summary=before_summary,
                actions_attempted=bool(execution["actions_attempted"]),
                validation_name="validation.qa-loop-step.candidate-approved-original-restored.json",
            )
            if restored:
                final_eval_path = restored["quality_eval_path"]
                final_eval = restored["quality_eval"]
                final_plan_path = restored["qa_loop_plan_path"]
                final_plan = restored["qa_loop_plan"]
                final_summary = restored["citation_summary"]
                final_progress = restored["progress"]
                final_verification = restored["verification"]
                execution["restored_current_verification"] = restored["verification"]
                execution["restored_current_state"] = {
                    "verification": restored["verification"],
                    "after": {"failing_codes": _failing_codes(final_eval), "citation_support_summary": final_summary},
                    "quality_eval_path": str(final_eval_path),
                    "qa_loop_plan_path": str(final_plan_path),
                    "qa_loop_plan_verdict": str(final_plan.get("verdict")),
                    "progress": final_progress,
                }
            verdict = "human_needed"
            execution["candidate_rollback"] = {
                "reason": "citation_candidate_auto_commit_blocked",
                "auto_commit_blocked_reason": auto_commit_reason,
                "failing_codes": sorted(after_codes),
            }
            execution["candidate_handoff"] = {
                "status": "human_needed_candidate_rejected_by_auto_commit_gate",
                "reason": "semi_auto citation repair did not satisfy the auto-commit safety gate",
                "candidate_path": citation_candidate_path,
                "auto_commit_blocked_reason": auto_commit_reason,
            }
            execution["candidate_state"] = candidate_state
            execution["candidate_progress"] = progress
        if (
            verdict == "continue"
            and execution["actions_attempted"]
            and not final_progress["forward_progress"]
            and not (citation_candidate_applied and progress.get("forward_progress"))
        ):
            verdict = "human_needed"
            execution["no_progress_override"] = True
    except Exception as exc:
        if citation_candidate_applied and paper_path and original_paper is not None:
            atomic_write_text(paper_path, original_paper)
            clear_pending_manuscript_write(cwd, status="restored", reason="qa_loop_candidate_exception")
            _restore_session_mutation_snapshot(cwd, mutation_snapshot)
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": "execution_error",
                "error": str(exc),
                "candidate_rollback": {"reason": "exception"} if citation_candidate_applied else None,
            }
        )
        path = _write_execution_artifact(cwd, execution)
        if execution["actions_attempted"]:
            append_quality_loop_history(
                cwd,
                before_eval,
                verdict="execution_error",
                plan_path=before_plan_path,
                quality_eval_path=before_eval_path,
                execution_path=path,
                event_type="qa_loop_step",
                consumes_budget=True,
            )
        return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code("execution_error"))
    execution.update(
        {
            "completed_at": utc_now_iso(),
            "verification": final_verification,
            "after": {"failing_codes": _failing_codes(final_eval), "citation_support_summary": final_summary},
            "progress": final_progress,
            "verdict": verdict,
        }
    )
    path = _write_execution_artifact(cwd, execution)
    if execution["actions_attempted"]:
        append_quality_loop_history(
            cwd,
            final_eval,
            verdict=verdict,
            plan_path=final_plan_path,
            quality_eval_path=final_eval_path,
            execution_path=path,
            event_type="qa_loop_step",
            consumes_budget=True,
            extra={"actionable_failure": execution.get("actionable_failure")} if execution.get("actionable_failure") else None,
        )
    return StepResult(path=path, payload=execution, exit_code=qa_loop_exit_code(verdict))
