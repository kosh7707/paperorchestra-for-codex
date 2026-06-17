from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.feedback.operator_context import _compact_metric_delta_records
from paperorchestra.feedback.operator_metrics import (
    _active_tier2_metric_delta,
    _claim_safe_tier2_metric_counts,
    _int_metric,
)
from paperorchestra.feedback.operator_contract import (
    AXIS_CATASTROPHIC_DROP,
    HUMAN_REVIEWABLE_NEW_TIER2_CODES,
    OVERALL_CATASTROPHIC_DROP,
)
from paperorchestra.feedback.packets import (
    _execution_payload_sha256,
    _file_sha256,
    _normalized_sha,
    _sha256_digest,
    _sha256_prefixed,
)


def _quality_failing_codes(quality_eval: dict[str, Any]) -> list[str]:
    result: list[str] = []
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return result
    for tier in tiers.values():
        if isinstance(tier, dict) and tier.get("status") in {"fail", "warn"}:
            result.extend(str(code) for code in tier.get("failing_codes") or [])
    return sorted(dict.fromkeys(result))


def _tier_failing_codes(quality_eval: dict[str, Any] | None, tier_name: str) -> list[str]:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
    if not isinstance(tier, dict):
        return []
    return sorted(dict.fromkeys(str(code) for code in tier.get("failing_codes") or []))


def _tier_status(quality_eval: dict[str, Any], tier_name: str) -> str:
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
    return str(tier.get("status") or "pass") if isinstance(tier, dict) else "pass"


def _candidate_hard_gate(
    *,
    validation_payload: dict[str, Any],
    compile_payload: dict[str, Any] | None,
    quality_eval: dict[str, Any],
    base_quality_eval: dict[str, Any] | None = None,
    quality_mode: str,
    incorporation: list[dict[str, Any]],
    candidate_result: dict[str, Any] | None,
    require_issue_progress: bool,
    manuscript_changed: bool,
    new_tier2_failures: list[str],
    base_active_failures: list[str],
    resolved_active_failures: list[str],
    allow_human_reviewable_new_tier2: bool = False,
    protected_supported_citation_regressions: list[dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not manuscript_changed:
        reasons.append("no_textual_change")
        failure_category = str((candidate_result or {}).get("executor_failure_category") or "none")
        if failure_category != "none":
            reasons.append("executor_crashed")
        else:
            reasons.append("executor_returned_identical_content")
    if not validation_payload.get("ok"):
        reasons.append("validation_failed")
    if compile_payload and not compile_payload.get("ok"):
        reasons.append("compile_failed")
    if _tier_status(quality_eval, "tier_0_preconditions") == "fail":
        reasons.append("tier0_failed")
    if _tier_status(quality_eval, "tier_1_structural") == "fail":
        reasons.append("tier1_failed")
    hard_new_tier2_failures = [
        code
        for code in new_tier2_failures
        if not (allow_human_reviewable_new_tier2 and code in HUMAN_REVIEWABLE_NEW_TIER2_CODES)
    ]
    if quality_mode == "claim_safe" and hard_new_tier2_failures:
        reasons.append("tier2_claim_safety_new_failures")
    metric_delta = _active_tier2_metric_delta(
        base_quality_eval,
        quality_eval,
        base_active_failures=base_active_failures,
    )
    if metric_delta.get("regressions"):
        reasons.append("active_tier2_metric_regression")
    if protected_supported_citation_regressions:
        reasons.append("protected_supported_citation_regression")
    metric_progress = bool(metric_delta.get("total_improved"))
    if (
        base_active_failures
        and not resolved_active_failures
        and not _candidate_reduces_citation_issue_count(candidate_result)
        and not metric_progress
    ):
        reasons.append("active_blocker_metric_progress_missing")
    if require_issue_progress and not any(item["status"] in {"reflected", "partially_reflected"} for item in incorporation):
        reasons.append("issue_progress_missing")
    if _catastrophic_review_regression(candidate_result):
        reasons.append("reviewer_catastrophic_regression")
    return not reasons, reasons


def _candidate_reduces_citation_issue_count(candidate_result: dict[str, Any] | None) -> bool:
    progress = candidate_result.get("candidate_progress") if isinstance(candidate_result, dict) else None
    if not isinstance(progress, dict):
        return False
    citation_issue_delta = progress.get("citation_issue_delta")
    return progress.get("forward_progress") is True and isinstance(citation_issue_delta, int) and citation_issue_delta < 0


def _candidate_attempt_ready_for_human_review(attempt: dict[str, Any]) -> bool:
    if not attempt.get("resolved_active_failures"):
        return False
    if not attempt.get("candidate_path"):
        return False
    if not Path(str(attempt.get("candidate_path"))).exists():
        return False
    disqualifying_reasons = {
        "no_textual_change",
        "executor_crashed",
        "executor_returned_identical_content",
        "validation_failed",
        "compile_failed",
        "tier0_failed",
        "tier1_failed",
        "active_blocker_metric_progress_missing",
        "active_blocker_progress_missing",
        "active_tier2_metric_regression",
        "protected_supported_citation_regression",
        "issue_progress_missing",
        "repeated_non_promotable_candidate",
        "reviewer_catastrophic_regression",
    }
    reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
    if reasons & disqualifying_reasons:
        return False
    new_tier2 = {str(code) for code in attempt.get("new_tier2_failures") or []}
    return new_tier2 <= HUMAN_REVIEWABLE_NEW_TIER2_CODES


def _best_human_review_candidate_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [attempt for attempt in attempts if _candidate_attempt_ready_for_human_review(attempt)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda attempt: (
            len(attempt.get("resolved_active_failures") or []),
            -len(attempt.get("candidate_active_failures") or []),
            -int(attempt.get("attempt_index") or 0),
        ),
    )


def _citation_issue_count_from_summary(summary: dict[str, Any] | None) -> int | None:
    if not isinstance(summary, dict):
        return None
    total = 0
    found = False
    for key in (
        "weakly_supported",
        "unsupported",
        "insufficient_evidence",
        "needs_manual_check",
        "manual_check",
        "contradicted",
        "metadata_only",
        "evidence_missing",
    ):
        value = summary.get(key)
        if isinstance(value, int):
            found = True
            total += value
    return total if found else None


def _attach_candidate_approval_from_attempt(
    execution: dict[str, Any],
    attempt: dict[str, Any],
    *,
    execution_path: Path,
) -> None:
    before_codes = [str(code) for code in attempt.get("base_active_failures") or []]
    after_codes = [str(code) for code in attempt.get("candidate_active_failures") or []]
    before_hash = _sha256_prefixed(execution.get("manuscript_sha256_before"))
    after_hash = _sha256_prefixed(_file_sha256(attempt.get("candidate_path")))
    verification = attempt.get("verification") if isinstance(attempt.get("verification"), dict) else {}
    citation_summary = None
    citation_block = verification.get("citation_support_review") if isinstance(verification, dict) else None
    if isinstance(citation_block, dict):
        citation_summary = citation_block.get("summary")
    active_metric_delta = attempt.get("active_tier2_metric_delta") if isinstance(attempt.get("active_tier2_metric_delta"), dict) else {}
    before_issue_count = active_metric_delta.get("base_total")
    after_issue_count = active_metric_delta.get("candidate_total")
    if not isinstance(before_issue_count, int) or not isinstance(after_issue_count, int):
        before_issue_count = None
        after_issue_count = _citation_issue_count_from_summary(citation_summary)
    progress = {
        "resolved_codes": [str(code) for code in attempt.get("resolved_active_failures") or []],
        "new_codes": [str(code) for code in attempt.get("candidate_active_failures") or [] if code not in before_codes],
        "before_failing_codes": before_codes,
        "after_failing_codes": after_codes,
        "before_manuscript_hash": before_hash,
        "after_manuscript_hash": after_hash,
        "same_manuscript_as_previous": before_hash == after_hash if before_hash and after_hash else None,
        "manuscript_identity_known": bool(before_hash and after_hash),
        "before_citation_issue_count": before_issue_count,
        "after_citation_issue_count": after_issue_count,
        "citation_issue_delta": (after_issue_count - before_issue_count) if isinstance(before_issue_count, int) and isinstance(after_issue_count, int) else None,
        "active_tier2_metric_delta": active_metric_delta,
        "forward_progress": True,
    }
    approval = {
        "status": "human_needed_candidate_ready",
        "candidate_path": attempt.get("candidate_path"),
        "candidate_sha256": _sha256_prefixed(_sha256_digest(str(attempt.get("candidate_sha256") or "")) or _file_sha256(attempt.get("candidate_path"))),
        "base_manuscript_sha256": before_hash,
        "source_execution_path": str(execution_path),
        "source_execution_sha256": "",
        "created_at": utc_now_iso(),
        "reason": "supervised operator candidate made net progress but introduced only human-reviewable claim-safety uncertainty",
    }
    execution["candidate_approval"] = approval
    execution["candidate_progress"] = progress
    execution["candidate_state"] = {
        "manuscript_path": attempt.get("candidate_path"),
        "verification": verification,
        "after": {
            "failing_codes": after_codes,
            "citation_support_summary": citation_summary,
        },
        "quality_eval_path": (verification.get("quality_eval") or {}).get("path") if isinstance(verification.get("quality_eval"), dict) else None,
        "qa_loop_plan_path": (verification.get("qa_loop_plan") or {}).get("path") if isinstance(verification.get("qa_loop_plan"), dict) else None,
        "qa_loop_plan_verdict": (verification.get("qa_loop_plan") or {}).get("verdict") if isinstance(verification.get("qa_loop_plan"), dict) else None,
        "progress": progress,
    }
    approval["source_execution_sha256"] = _execution_payload_sha256(execution)


def _catastrophic_review_regression(candidate_result: dict[str, Any] | None) -> bool:
    if not candidate_result:
        return False
    before = candidate_result.get("score_before")
    after = candidate_result.get("score_after")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and float(after) < float(before) - OVERALL_CATASTROPHIC_DROP:
        return True
    before_axes = candidate_result.get("axis_scores_before") or {}
    after_axes = candidate_result.get("axis_scores_after") or {}
    if isinstance(before_axes, dict) and isinstance(after_axes, dict):
        for key in set(before_axes) & set(after_axes):
            if isinstance(before_axes.get(key), (int, float)) and isinstance(after_axes.get(key), (int, float)):
                if float(after_axes[key]) < float(before_axes[key]) - AXIS_CATASTROPHIC_DROP:
                    return True
    return False


def _actionable_failure(owner_categories: list[str], reason: str, *, execution_error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "reason": reason,
        "owner_categories": sorted(dict.fromkeys(owner_categories or ["author"])),
    }
    if execution_error:
        payload["execution_error"] = execution_error
    return payload


def _compact_operator_attempt_failure(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic, code-only diagnostics from the latest operator attempt.

    Operator candidates can contain manuscript text or sensitive source paths.
    This helper intentionally copies only compact failure-code style fields from
    the latest attempt so execution/history consumers can detect repeated hard
    gate failures without leaking candidate content.
    """
    latest = attempts[-1] if attempts else {}
    if not isinstance(latest, dict):
        latest = {}

    def _strings(key: str) -> list[str]:
        return sorted(
            dict.fromkeys(
                str(value)
                for value in latest.get(key) or []
                if str(value).strip()
            )
        )

    payload: dict[str, Any] = {
        "attempt_index": latest.get("attempt_index"),
        "latest_gate_reasons": _strings("gate_reasons"),
        "new_tier2_failures": _strings("new_tier2_failures"),
        "resolved_active_failures": _strings("resolved_active_failures"),
        "candidate_active_failures": _strings("candidate_active_failures"),
        "base_active_failures": _strings("base_active_failures"),
    }
    executor_failure = str(latest.get("executor_failure_category") or "").strip()
    if executor_failure:
        payload["executor_failure_category"] = executor_failure
    blocked_progress = _compact_blocked_candidate_progress(latest)
    if blocked_progress:
        payload["blocked_candidate_progress"] = blocked_progress
    return payload


def _compact_blocked_candidate_progress(attempt: dict[str, Any]) -> dict[str, Any] | None:
    """Return safe diagnostics for candidates that improved but could not promote.

    The payload is intentionally code/count-only.  It must not include candidate
    paths, manuscript text, source excerpts, or raw source-obligation item ids.
    """
    if not isinstance(attempt, dict) or attempt.get("gate_passed") is True:
        return None
    metric_delta = attempt.get("active_tier2_metric_delta")
    if not isinstance(metric_delta, dict):
        metric_delta = {}
    improvements = _compact_metric_delta_records(metric_delta.get("improvements"))
    regressions = _compact_metric_delta_records(metric_delta.get("regressions"))
    resolved = sorted(dict.fromkeys(str(code) for code in attempt.get("resolved_active_failures") or [] if str(code).strip()))
    gate_reasons = sorted(dict.fromkeys(str(reason) for reason in attempt.get("gate_reasons") or [] if str(reason).strip()))
    new_tier2 = sorted(dict.fromkeys(str(code) for code in attempt.get("new_tier2_failures") or [] if str(code).strip()))
    total_improved = metric_delta.get("total_improved") is True
    if not (improvements or resolved or total_improved):
        return None
    base_total = metric_delta.get("base_total")
    candidate_total = metric_delta.get("candidate_total")
    payload: dict[str, Any] = {
        "kind": "active_metric_improved_but_blocked",
        "blocking_gate_reasons": gate_reasons,
        "new_tier2_failures": new_tier2,
        "resolved_active_failures": resolved,
        "metric_improvements": improvements,
        "metric_regressions": regressions,
        "base_total": base_total if isinstance(base_total, int) else None,
        "candidate_total": candidate_total if isinstance(candidate_total, int) else None,
        "total_improved": total_improved,
    }
    if new_tier2:
        payload["recommended_next_focus"] = new_tier2
    return payload


def _repeats_non_promotable_candidate(
    prior_attempts: list[dict[str, Any]],
    candidate_sha256: str | None,
) -> bool:
    candidate_sha = _normalized_sha(candidate_sha256)
    if not candidate_sha:
        return False
    for prior in prior_attempts:
        if not isinstance(prior, dict):
            continue
        if prior.get("gate_passed") is True:
            continue
        prior_sha = _normalized_sha(prior.get("candidate_sha256"))
        prior_reasons = [str(reason) for reason in prior.get("gate_reasons") or [] if str(reason).strip()]
        if prior_sha and prior_sha == candidate_sha and prior_reasons:
            return True
    return False


def _operator_actionable_failure(
    owner_categories: list[str],
    reason: str,
    *,
    category: str,
    code: str,
    attempts: list[dict[str, Any]] | None = None,
    execution_error: str | None = None,
) -> dict[str, Any]:
    payload = _actionable_failure(owner_categories, reason, execution_error=execution_error)
    payload.update(
        {
            "category": category,
            "code": code,
            "next_steps": [
                "Inspect latest_gate_reasons before retrying operator feedback.",
                "Address new Tier 2 failures before promoting a candidate.",
                "Avoid identical or no-progress candidates; rerun the QA loop after targeted changes.",
            ],
        }
    )
    payload.update(_compact_operator_attempt_failure(attempts or []))
    return payload


