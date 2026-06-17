from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.feedback.operator_contract import (
    OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION,
    OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION,
    OPERATOR_SOURCE,
)
from paperorchestra.feedback.packets import _file_sha256


def _build_operator_execution_record(
    imported_path: str | Path,
    imported: dict[str, Any],
    *,
    current_sha: str,
    max_supervised_iterations: int,
    intent: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION,
        "started_at": utc_now_iso(),
        "event_type": "operator_feedback_cycle",
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "imported_feedback_path": str(Path(imported_path).resolve()),
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
        record["human_needed_answer"] = dict(imported["human_needed_answer"])
    if isinstance(imported.get("operator_review_notes"), dict):
        record["operator_review_notes"] = dict(imported["operator_review_notes"])
    return record


def _build_operator_attempt_record(
    *,
    attempt_index: int,
    intent: str,
    candidate_result: dict[str, Any],
    candidate_sha_for_attempt: str,
    gate_passed: bool,
    gate_reasons: list[str],
    base_tier2_failures: set[str],
    candidate_tier2_failures: set[str],
    new_tier2_failures: list[str],
    base_active_failures: set[str],
    candidate_active_failures: set[str],
    resolved_active_failures: list[str],
    active_tier2_metric_delta: dict[str, Any],
    protected_regressions: list[dict[str, Any]],
    verification_block: dict[str, Any],
    incorporation: list[dict[str, Any]],
) -> dict[str, Any]:
    record = {
        "attempt_index": attempt_index,
        "candidate_branch": intent,
        "candidate_path": candidate_result.get("candidate_path"),
        "candidate_sha256": candidate_sha_for_attempt,
        "gate_passed": gate_passed,
        "gate_reasons": gate_reasons,
        "base_tier2_failures": sorted(base_tier2_failures),
        "candidate_tier2_failures": sorted(candidate_tier2_failures),
        "new_tier2_failures": new_tier2_failures,
        "base_active_failures": sorted(base_active_failures),
        "candidate_active_failures": sorted(candidate_active_failures),
        "resolved_active_failures": resolved_active_failures,
        "active_tier2_metric_delta": active_tier2_metric_delta,
        "protected_supported_citation_regressions": protected_regressions,
        "protected_supported_citation_regression_count": len(protected_regressions),
        "verification": verification_block,
        "incorporation": incorporation,
        "executor_environment": candidate_result.get("executor_environment")
        or ("preexisting_candidate" if intent == "approve_existing_candidate" else "in_process"),
        "executor_path": candidate_result.get("executor_path")
        or (
            "operator_feedback._ready_candidate_from_packet"
            if intent == "approve_existing_candidate"
            else "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper"
        ),
        "executor_trace_artifact": candidate_result.get("executor_trace_artifact"),
        "executor_failure_category": candidate_result.get("executor_failure_category") or "none",
    }
    if candidate_result.get("preserved_prior_after_contract_regression") is True:
        record["preserved_prior_after_contract_regression"] = True
        for key in (
            "rejected_candidate_path",
            "rejected_candidate_sha256",
            "contract_regression_issue_count",
            "contract_regression_validation_report_path",
        ):
            if candidate_result.get(key) is not None:
                record[key] = candidate_result[key]
    return record


def _build_operator_incorporation_report(
    *,
    imported: dict[str, Any],
    current_sha: str,
    after_sha: str,
    promotion_status: str,
    actionable_failure: dict[str, Any] | None,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "packet_sha256": imported.get("packet_sha256"),
        "manuscript_sha256_before": current_sha,
        "manuscript_sha256_after": after_sha,
        "promotion_status": promotion_status,
        "actionable_failure": actionable_failure,
        "issues": issues,
    }
    if isinstance(imported.get("human_needed_answer"), dict):
        report["human_needed_answer"] = dict(imported["human_needed_answer"])
    if isinstance(imported.get("operator_review_notes"), dict):
        report["operator_review_notes"] = dict(imported["operator_review_notes"])
    return report


def _operator_feedback_verdict(*, executor_crashed: bool, promoted: bool, plan: dict[str, Any]) -> str:
    if executor_crashed:
        return "execution_error"
    if promoted:
        return str(plan.get("verdict") or "human_needed")
    return "human_needed"
