from __future__ import annotations

from typing import Any

from paperorchestra.feedback.operator_context import _compact_metric_delta_records
from paperorchestra.feedback.packets import _normalized_sha


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

    The payload is intentionally code/count-only. It must not include candidate
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
