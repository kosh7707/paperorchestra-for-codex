from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.io import write_json
from paperorchestra.runtime.providers import BaseProvider
from paperorchestra.loop_engine.quality.loop import append_quality_loop_history
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.feedback.operator_execution import (
    _verification_snapshot,
    _verification_block,
    _load_packet_from_imported,
    _packet_artifact_payload,
    _packet_prior_operator_attempts,
    _candidate_approval_source_role,
    _ready_candidate_from_packet,
    _stage_candidate_text_for_verification,
    _preserve_operator_candidate_for_attempt,
    _promote_candidate_text,
    _generate_operator_candidate,
    _failed_operator_candidate_result,
)
from paperorchestra.feedback.operator_context import (
    _write_operator_review_for_refiner,
)
from paperorchestra.feedback.operator_gates import (
    _active_tier2_metric_delta,
    _attach_candidate_approval_from_attempt,
    _best_human_review_candidate_attempt,
    _candidate_hard_gate,
    _operator_actionable_failure,
    _quality_failing_codes,
    _repeats_non_promotable_candidate,
    _tier_failing_codes,
)
from paperorchestra.feedback.operator_incorporation import _issue_incorporation_detailed
from paperorchestra.feedback.operator_snapshots import _restore_session_snapshot, _session_snapshot
from paperorchestra.feedback.operator_contract import (
    ACTIONABLE_FAILURE_OWNER_CATEGORIES,
    AXIS_CATASTROPHIC_DROP,
    HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS,
    HUMAN_REVIEWABLE_NEW_TIER2_CODES,
    OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION,
    OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION,
    OPERATOR_FEEDBACK_INTENTS,
    OPERATOR_FEEDBACK_SCHEMA_VERSION,
    OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES,
    OPERATOR_SOURCE,
    OVERALL_CATASTROPHIC_DROP,
    _load_imported_feedback,
    _read_packet,
    build_operator_review_packet,
    derive_operator_issue_id,
    import_operator_feedback,
    validate_operator_review_notes,
)
from paperorchestra.feedback.packets import (
    _file_sha256,
    _sha256_digest,
    _sha256_prefixed,
)
from paperorchestra.core.errors import ContractError


def apply_operator_feedback(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    imported_feedback_path: str | Path,
    max_supervised_iterations: int = 1,
    require_compile: bool = False,
    quality_mode: str = "claim_safe",
    max_iterations: int = 10,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    if max_supervised_iterations < 1:
        raise ContractError("max_supervised_iterations must be >= 1")
    imported_path = Path(imported_feedback_path).resolve()
    imported = _load_imported_feedback(imported_path)
    packet = _load_packet_from_imported(imported)
    intent = str(imported.get("intent") or "")
    state = load_session(cwd)
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha != imported.get("manuscript_sha256"):
        raise ContractError("imported operator feedback is stale for the current manuscript")
    base_quality_eval = _packet_artifact_payload(packet, "quality_eval")
    packet_prior_attempts = _packet_prior_operator_attempts(packet)
    base_tier2_failures = set(_tier_failing_codes(base_quality_eval, "tier_2_claim_safety"))
    base_active_failures = set(_quality_failing_codes(base_quality_eval or {}))

    execution: dict[str, Any] = {
        "schema_version": OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION,
        "started_at": utc_now_iso(),
        "event_type": "operator_feedback_cycle",
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "imported_feedback_path": str(imported_path),
        "imported_feedback_sha256": _file_sha256(imported_path),
        "packet_sha256": imported.get("packet_sha256"),
        "manuscript_sha256_before": current_sha,
        "supervised_max_iterations": max_supervised_iterations,
        "translated_actions": imported.get("translated_actions") or [],
        "candidate_branch": intent,
        "promotion_status": "candidate_ready",
        "post_promotion_qa_verdict": None,
        "attempts": [],
        "verification": {},
    }
    if isinstance(imported.get("human_needed_answer"), dict):
        execution["human_needed_answer"] = dict(imported["human_needed_answer"])
    if isinstance(imported.get("operator_review_notes"), dict):
        execution["operator_review_notes"] = dict(imported["operator_review_notes"])
    snapshot = _session_snapshot(cwd)
    before_text = snapshot.get("paper_text") or ""
    owner_categories = [str(issue.get("owner_category") or "author") for issue in imported.get("issues") or []]
    final_incorporation: list[dict[str, Any]] = []
    final_verification: dict[str, Any] | None = None
    final_candidate_result: dict[str, Any] | None = None

    try:
        attempts = 0 if intent == "reject_candidate_with_reason" else 1 if intent == "approve_existing_candidate" else max_supervised_iterations
        for attempt_index in range(1, attempts + 1):
            _restore_session_snapshot(cwd, snapshot)
            if intent == "approve_existing_candidate":
                candidate_result = _ready_candidate_from_packet(
                    packet,
                    current_sha,
                    source_artifact_role=_candidate_approval_source_role(imported),
                )
                candidate_text = _stage_candidate_text_for_verification(cwd, candidate_result["candidate_path"])
                require_issue_progress = False
            elif intent == "generate_new_operator_candidate":
                prior_attempts_for_candidate = [*packet_prior_attempts, *(execution.get("attempts") or [])]
                try:
                    candidate_result = _generate_operator_candidate(
                        cwd,
                        provider,
                        imported,
                        require_compile=require_compile,
                        runtime_mode=runtime_mode,
                        quality_mode=quality_mode,
                        prior_attempts=prior_attempts_for_candidate,
                    )
                except Exception as exc:
                    _restore_session_snapshot(cwd, snapshot)
                    candidate_result = _failed_operator_candidate_result(cwd, exc)
                candidate_text = candidate_result.get("candidate_text") or ""
                if candidate_result.get("candidate_path"):
                    candidate_result = _preserve_operator_candidate_for_attempt(
                        cwd,
                        candidate_result,
                        attempt_index=attempt_index,
                    )
                    candidate_text = _stage_candidate_text_for_verification(cwd, candidate_result["candidate_path"])
                require_issue_progress = True
            elif intent == "reject_candidate_with_reason":  # pragma: no cover - attempts is zero for explicit rejection
                break
            else:  # pragma: no cover - import validation should prevent this
                raise ContractError(f"unsupported imported operator intent: {intent}")

            verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=require_compile,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name=f"validation.operator-feedback.attempt-{attempt_index:02d}.json",
            )
            blocking_codes = _quality_failing_codes(verification["quality_eval"])
            candidate_tier2_failures = set(_tier_failing_codes(verification["quality_eval"], "tier_2_claim_safety"))
            candidate_active_failures = set(blocking_codes)
            new_tier2_failures = sorted(candidate_tier2_failures - base_tier2_failures)
            resolved_active_failures = sorted(base_active_failures - candidate_active_failures)
            incorporation_blocking_codes = [code for code in blocking_codes if code not in base_tier2_failures]
            incorporation = _issue_incorporation_detailed(imported.get("issues") or [], before_text, candidate_text, blocking_codes=incorporation_blocking_codes)
            candidate_sha = _file_sha256(load_session(cwd).artifacts.paper_full_tex)
            protected_regressions = _protected_supported_citation_regressions(imported, candidate_text)
            ok, gate_reasons = _candidate_hard_gate(
                validation_payload=verification["validation_payload"],
                compile_payload=verification["compile_payload"],
                quality_eval=verification["quality_eval"],
                base_quality_eval=base_quality_eval,
                quality_mode=quality_mode,
                incorporation=incorporation,
                candidate_result=candidate_result,
                require_issue_progress=require_issue_progress,
                manuscript_changed=candidate_sha != current_sha,
                new_tier2_failures=new_tier2_failures,
                base_active_failures=sorted(base_active_failures),
                resolved_active_failures=resolved_active_failures,
                allow_human_reviewable_new_tier2=intent == "approve_existing_candidate",
                protected_supported_citation_regressions=protected_regressions,
            )
            if candidate_result.get("preserved_prior_after_contract_regression") is True:
                gate_reasons = list(dict.fromkeys([*gate_reasons, "contract_regression_preserved_prior"]))
                ok = False
            candidate_sha_for_attempt = _sha256_prefixed(_sha256_digest(str(candidate_result.get("candidate_sha256") or "")) or _file_sha256(candidate_result.get("candidate_path")))
            if not ok and _repeats_non_promotable_candidate([*packet_prior_attempts, *(execution.get("attempts") or [])], candidate_sha_for_attempt):
                gate_reasons = list(dict.fromkeys([*gate_reasons, "repeated_non_promotable_candidate"]))
                ok = False
            attempt_record = {
                "attempt_index": attempt_index,
                "candidate_branch": intent,
                "candidate_path": candidate_result.get("candidate_path"),
                "candidate_sha256": candidate_sha_for_attempt,
                "gate_passed": ok,
                "gate_reasons": gate_reasons,
                "base_tier2_failures": sorted(base_tier2_failures),
                "candidate_tier2_failures": sorted(candidate_tier2_failures),
                "new_tier2_failures": new_tier2_failures,
                "base_active_failures": sorted(base_active_failures),
                "candidate_active_failures": sorted(candidate_active_failures),
                "resolved_active_failures": resolved_active_failures,
                "active_tier2_metric_delta": _active_tier2_metric_delta(
                    base_quality_eval,
                    verification["quality_eval"],
                    base_active_failures=sorted(base_active_failures),
                ),
                "protected_supported_citation_regressions": protected_regressions,
                "protected_supported_citation_regression_count": len(protected_regressions),
                "verification": _verification_block(verification),
                "incorporation": incorporation,
                "executor_environment": candidate_result.get("executor_environment") or ("preexisting_candidate" if intent == "approve_existing_candidate" else "in_process"),
                "executor_path": candidate_result.get("executor_path") or ("operator_feedback._ready_candidate_from_packet" if intent == "approve_existing_candidate" else "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper"),
                "executor_trace_artifact": candidate_result.get("executor_trace_artifact"),
                "executor_failure_category": candidate_result.get("executor_failure_category") or "none",
            }
            if candidate_result.get("preserved_prior_after_contract_regression") is True:
                attempt_record["preserved_prior_after_contract_regression"] = True
                for key in (
                    "rejected_candidate_path",
                    "rejected_candidate_sha256",
                    "contract_regression_issue_count",
                    "contract_regression_validation_report_path",
                ):
                    if candidate_result.get(key) is not None:
                        attempt_record[key] = candidate_result[key]
            execution["attempts"].append(attempt_record)
            final_incorporation = incorporation
            final_verification = verification
            final_candidate_result = candidate_result
            if ok:
                execution["promotion_status"] = "promoted"
                execution["promotion_reason"] = "operator_candidate_passed_hard_gate"
                _promote_candidate_text(cwd, candidate_result["candidate_path"], snapshot.get("paper_path"))
                promoted_verification = _verification_snapshot(
                    cwd,
                    provider=provider,
                    require_compile=require_compile,
                    quality_mode=quality_mode,
                    max_iterations=max_iterations,
                    require_live_verification=require_live_verification,
                    accept_mixed_provenance=accept_mixed_provenance,
                    runtime_mode=runtime_mode,
                    citation_evidence_mode=citation_evidence_mode,
                    citation_provider_name=citation_provider_name,
                    citation_provider_command=citation_provider_command,
                    validation_name=f"validation.operator-feedback.promoted-{attempt_index:02d}.json",
                )
                final_verification = promoted_verification
                execution["post_promotion_qa_verdict"] = str(promoted_verification["plan"].get("verdict"))
                attempt_record["promoted_canonical_verification"] = _verification_block(promoted_verification)
                break
        else:
            _restore_session_snapshot(cwd, snapshot)
            rollback_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=require_compile,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.rollback.json",
            )
            final_verification = rollback_verification
            explicit_rejection = intent == "reject_candidate_with_reason"
            execution["promotion_status"] = "rolled_back"
            execution["promotion_reason"] = "operator_rejected_candidate" if explicit_rejection else "operator_candidate_failed_hard_gate"
            execution["candidate_rollback"] = {
                "reason": "operator_rejected_candidate" if explicit_rejection else "supervised_candidate_failed_hard_gate",
                "restored_verification": _verification_block(rollback_verification),
            }

        execution_path = artifact_path(cwd, "operator_feedback.execution.json")
        promoted = execution["promotion_status"] == "promoted"
        executor_crashed = any(
            str(attempt.get("executor_failure_category") or "none") != "none"
            for attempt in execution.get("attempts") or []
        )
        if not promoted and final_verification is None:
            final_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=False,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.no-promotion.json",
            )
        final_state = load_session(cwd)
        after_sha = _file_sha256(final_state.artifacts.paper_full_tex)
        if executor_crashed:
            failure_reason = "supervised operator feedback command failed"
            failure_category = "operator_execution_error"
            failure_code = "operator_executor_crashed"
        elif intent == "reject_candidate_with_reason":
            failure_reason = "operator feedback explicitly rejected the candidate"
            failure_category = "operator_rejected_candidate"
            failure_code = "operator_rejected_candidate"
        else:
            failure_reason = "operator feedback did not produce an acceptable canonical manuscript update"
            failure_category = "operator_candidate_failed_hard_gate"
            failure_code = str(execution.get("promotion_reason") or "operator_candidate_failed_hard_gate")
        non_promoted_actionable_failure = None if promoted else _operator_actionable_failure(
            owner_categories,
            failure_reason,
            category=failure_category,
            code=failure_code,
            attempts=execution.get("attempts") or [],
        )
        incorporation_report = {
            "schema_version": OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION,
            "generated_at": utc_now_iso(),
            "source": OPERATOR_SOURCE,
            "not_independent_human_review": True,
            "packet_sha256": imported.get("packet_sha256"),
            "manuscript_sha256_before": current_sha,
            "manuscript_sha256_after": after_sha,
            "promotion_status": execution["promotion_status"],
            "actionable_failure": non_promoted_actionable_failure,
            "issues": final_incorporation,
        }
        if isinstance(imported.get("human_needed_answer"), dict):
            incorporation_report["human_needed_answer"] = dict(imported["human_needed_answer"])
        if isinstance(imported.get("operator_review_notes"), dict):
            incorporation_report["operator_review_notes"] = dict(imported["operator_review_notes"])
        incorporation_path = artifact_path(cwd, "operator_feedback.incorporation.json")
        write_json(incorporation_path, incorporation_report)
        plan = final_verification["plan"] if final_verification else {}
        verdict = "execution_error" if executor_crashed else str(plan.get("verdict") or "human_needed") if promoted else "human_needed"
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": verdict,
                "supervised_iteration_index": len(execution["attempts"]),
                "supervised_remaining": max(max_supervised_iterations - len(execution["attempts"]), 0),
                "supervised_budget_exhausted": not promoted and len(execution["attempts"]) >= max_supervised_iterations,
                "manuscript_sha256_after": after_sha,
                "candidate_result": final_candidate_result,
                "incorporation_report": str(incorporation_path),
                "verification": _verification_block(final_verification) if final_verification else {},
                "actionable_failure": non_promoted_actionable_failure,
            }
        )
        if not promoted:
            best_attempt = _best_human_review_candidate_attempt(execution.get("attempts") or [])
            if best_attempt is not None:
                _attach_candidate_approval_from_attempt(
                    execution,
                    best_attempt,
                    execution_path=execution_path,
                )
        if executor_crashed:
            execution["error"] = "operator executor crashed during supervised feedback application"
        write_json(execution_path, execution)
        if final_verification:
            append_quality_loop_history(
                cwd,
                final_verification["quality_eval"],
                verdict=verdict,
                plan_path=final_verification["plan_path"],
                quality_eval_path=final_verification["quality_path"],
                execution_path=execution_path,
                event_type="operator_feedback_cycle",
                consumes_budget=False,
                extra={
                    "supervised_iteration_index": execution["supervised_iteration_index"],
                    "supervised_max_iterations": execution["supervised_max_iterations"],
                    "supervised_remaining": execution["supervised_remaining"],
                    "supervised_budget_exhausted": execution["supervised_budget_exhausted"],
                    "promotion_status": execution["promotion_status"],
                    "post_promotion_qa_verdict": execution["post_promotion_qa_verdict"],
                    "actionable_failure": non_promoted_actionable_failure,
                },
            )
        return execution_path, execution
    except Exception as exc:
        _restore_session_snapshot(cwd, snapshot)
        rollback_verification: dict[str, Any] | None = None
        try:
            rollback_verification = _verification_snapshot(
                cwd,
                provider=provider,
                require_compile=False,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
                require_live_verification=require_live_verification,
                accept_mixed_provenance=accept_mixed_provenance,
                runtime_mode=runtime_mode,
                citation_evidence_mode=citation_evidence_mode,
                citation_provider_name=citation_provider_name,
                citation_provider_command=citation_provider_command,
                validation_name="validation.operator-feedback.exception-rollback.json",
            )
        except Exception as verify_exc:  # pragma: no cover - defensive evidence best-effort
            rollback_verification = {"error": type(verify_exc).__name__ + ": " + str(verify_exc)}
        restored_block: dict[str, Any] = {}
        if rollback_verification and "validation_path" in rollback_verification:
            restored_block = _verification_block(rollback_verification)
        elif rollback_verification:
            restored_block = {"error": rollback_verification.get("error")}
        exception_actionable_failure = _operator_actionable_failure(
            owner_categories,
            "supervised operator feedback command failed",
            category="operator_execution_error",
            code="supervised_operator_feedback_command_failed",
            attempts=execution.get("attempts") or [],
            execution_error=type(exc).__name__ + ": " + str(exc),
        )
        exception_history_actionable_failure = _operator_actionable_failure(
            owner_categories,
            "supervised operator feedback command failed",
            category="operator_execution_error",
            code="supervised_operator_feedback_command_failed",
            attempts=execution.get("attempts") or [],
        )
        exception_history_actionable_failure["error_type"] = type(exc).__name__
        execution.update(
            {
                "completed_at": utc_now_iso(),
                "verdict": "execution_error",
                "promotion_status": "rolled_back",
                "post_promotion_qa_verdict": None,
                "error": str(exc),
                "candidate_rollback": {"reason": "exception", "restored_verification": restored_block},
                "verification": {"restored_after_exception": restored_block},
                "actionable_failure": exception_actionable_failure,
            }
        )
        execution_path = artifact_path(cwd, "operator_feedback.execution.json")
        write_json(execution_path, execution)
        if rollback_verification and "quality_eval" in rollback_verification:
            append_quality_loop_history(
                cwd,
                rollback_verification["quality_eval"],
                verdict="execution_error",
                plan_path=rollback_verification["plan_path"],
                quality_eval_path=rollback_verification["quality_path"],
                execution_path=execution_path,
                event_type="operator_feedback_cycle",
                consumes_budget=False,
                extra={
                    "supervised_iteration_index": len(execution.get("attempts") or []) or 1,
                    "supervised_max_iterations": execution["supervised_max_iterations"],
                    "supervised_remaining": max(execution["supervised_max_iterations"] - (len(execution.get("attempts") or []) or 1), 0),
                    "supervised_budget_exhausted": True,
                    "execution_error_type": type(exc).__name__,
                    "promotion_status": "rolled_back",
                    "actionable_failure": exception_history_actionable_failure,
                },
            )
        return execution_path, execution
