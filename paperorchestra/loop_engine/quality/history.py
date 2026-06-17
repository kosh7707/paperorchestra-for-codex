from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .policy import BUDGET_CONSUMING_HISTORY_EVENTS, HISTORY_FILENAME
from paperorchestra.core.session import runtime_root

def quality_loop_history_path(cwd: str | Path | None) -> Path:
    return runtime_root(cwd) / HISTORY_FILENAME


def _read_quality_history(cwd: str | Path | None) -> list[dict[str, Any]]:
    path = quality_loop_history_path(cwd)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _history_entry_consumes_budget(entry: dict[str, Any]) -> bool:
    if "consumes_budget" in entry:
        return bool(entry.get("consumes_budget"))
    return str(entry.get("event_type") or "") in BUDGET_CONSUMING_HISTORY_EVENTS


def _actionable_failure_signature(entry: dict[str, Any]) -> dict[str, Any] | None:
    failure = entry.get("actionable_failure")
    if not isinstance(failure, dict):
        return None
    category = str(failure.get("category") or "").strip()
    code = str(failure.get("code") or "").strip()
    reason = str(failure.get("reason") or "").strip()
    validation_codes = sorted(
        {
            str(code).strip()
            for code in failure.get("validation_failing_codes") or []
            if str(code).strip()
        }
    )
    if not any([category, code, reason, validation_codes]):
        return None
    return {
        "category": category,
        "code": code,
        "reason": reason,
        "validation_failing_codes": validation_codes,
    }


def _repeated_actionable_failure(budget_history: list[dict[str, Any]]) -> dict[str, Any]:
    signatures = [_actionable_failure_signature(entry) for entry in budget_history]
    signatures = [signature for signature in signatures if signature]
    if len(signatures) < 2:
        return {"detected": False, "count": len(signatures), "signature": signatures[-1] if signatures else None}
    latest = signatures[-1]
    count = 1
    for signature in reversed(signatures[:-1]):
        if signature != latest:
            break
        count += 1
    return {"detected": count >= 2, "count": count, "signature": latest}


def operator_feedback_cycle_count(cwd: str | Path | None, session_id: str | None = None) -> int:
    if session_id is None:
        current_session = runtime_root(cwd) / "current_session.txt"
        if current_session.exists():
            session_id = current_session.read_text(encoding="utf-8").strip() or None
    return sum(
        1
        for entry in _read_quality_history(cwd)
        if entry.get("event_type") == "operator_feedback_cycle"
        and (session_id is None or entry.get("session_id") == session_id)
    )
def _failing_codes_from_quality_eval(quality_eval: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    non_reviewable = quality_eval.get("non_reviewable") if isinstance(quality_eval, dict) else {}
    if isinstance(non_reviewable, dict):
        for code in non_reviewable.get("failing_codes") or []:
            codes.append(str(code))
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if not isinstance(tiers, dict):
        return codes
    for key, tier in tiers.items():
        if not str(key).startswith("tier_") or not isinstance(tier, dict):
            continue
        status = tier.get("status")
        if status not in {"fail", "warn"}:
            continue
        for code in tier.get("failing_codes") or []:
            codes.append(str(code))
    return sorted(dict.fromkeys(codes))


def _tier_statuses(quality_eval: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    tiers = quality_eval.get("tiers") if isinstance(quality_eval, dict) else {}
    if isinstance(tiers, dict):
        for key, tier in tiers.items():
            if isinstance(tier, dict) and str(key).startswith("tier_"):
                statuses[key] = str(tier.get("status"))
    return statuses


def _resolve_axis_drop_tolerance(default: float = 0.0) -> float:
    raw = os.environ.get("PAPERO_QA_LOOP_AXIS_DROP_TOLERANCE")
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _build_cross_iteration(
    cwd: str | Path | None,
    session_id: str | None,
    manuscript_hash: str | None,
    current_failing_codes: list[str],
    max_iterations: int,
    *,
    current_axis_scores: dict[str, float] | None = None,
    current_attempt_consumes_budget: bool = False,
) -> dict[str, Any]:
    history = [
        entry
        for entry in _read_quality_history(cwd)
        if not session_id or entry.get("session_id") == session_id
    ]
    budget_history = [entry for entry in history if _history_entry_consumes_budget(entry)]
    attempts_used_before = len(budget_history)
    attempts_used = attempts_used_before + (1 if current_attempt_consumes_budget else 0)
    iteration_index = attempts_used if current_attempt_consumes_budget else attempts_used + 1
    previous = budget_history[-1] if budget_history else None
    previous_codes = set(previous.get("failing_codes") or []) if isinstance(previous, dict) else set()
    current_codes = set(current_failing_codes)
    previous_axes = previous.get("tier_3_axis_scores") if isinstance(previous, dict) and isinstance(previous.get("tier_3_axis_scores"), dict) else {}
    current_axes = current_axis_scores or {}
    axis_drops: list[dict[str, Any]] = []
    tolerance = _resolve_axis_drop_tolerance()
    for axis, previous_score in previous_axes.items():
        current_score = current_axes.get(axis)
        if isinstance(previous_score, (int, float)) and isinstance(current_score, (int, float)):
            drop = float(previous_score) - float(current_score)
            if drop > tolerance:
                axis_drops.append({"axis": axis, "previous": float(previous_score), "current": float(current_score), "drop": round(drop, 4), "tolerance": tolerance})
    oscillation_detected = False
    flapping_codes: list[str] = []
    if len(budget_history) >= 2:
        two_back = set(budget_history[-2].get("failing_codes") or [])
        one_back = set(budget_history[-1].get("failing_codes") or [])
        if current_codes == two_back and current_codes != one_back:
            oscillation_detected = True
            flapping_codes = sorted(current_codes | one_back)
    same_manuscript_as_previous = bool(previous and manuscript_hash and previous.get("manuscript_hash") == manuscript_hash)
    forward_progress = not (bool(current_codes) and current_codes == previous_codes)
    if same_manuscript_as_previous and current_codes:
        forward_progress = False
    return {
        "iteration_index": iteration_index,
        "budget": {
            "max": max_iterations,
            "remaining": max(max_iterations - attempts_used, 0),
            "attempts_used": attempts_used,
            "attempts_used_before_current": attempts_used_before,
            "current_attempt_consumes_budget": current_attempt_consumes_budget,
        },
        "regression": {
            "vs_previous_manuscript_hash": previous.get("manuscript_hash") if isinstance(previous, dict) else None,
            "same_manuscript_as_previous": same_manuscript_as_previous,
            "new_failing_codes": sorted(current_codes - previous_codes),
            "resolved_failing_codes": sorted(previous_codes - current_codes),
            "tier_3_axis_drops": axis_drops,
            "oscillation": {"detected": oscillation_detected, "flapping_codes": flapping_codes},
            "forward_progress": forward_progress,
            "repeated_actionable_failure": _repeated_actionable_failure(budget_history),
        },
    }
