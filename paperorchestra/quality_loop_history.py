from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .quality_loop_policy import BUDGET_CONSUMING_HISTORY_EVENTS, HISTORY_FILENAME
from .session import runtime_root

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


def operator_feedback_cycle_count_from_commands(commands_path: str | Path) -> int:
    """Count operator-feedback apply cycles from a readable smoke command ledger."""
    path = Path(commands_path)
    if not path.exists():
        return 0
    names = set(re.findall(r"`operator_apply_cycle_(\d+)`", path.read_text(encoding="utf-8")))
    return len(names)


def validate_smoke_bundle_operator_feedback_cycles(evidence_root: str | Path) -> dict[str, Any]:
    """Validate that smoke summary counters agree with command evidence.

    This is intentionally bundle-shape based rather than tied to one historical
    historical run: any future live-smoke bundle that writes
    `readable/commands.md` and `readable/verdict.json` can be checked with the
    same invariant.
    """
    root = Path(evidence_root)
    commands_path = root / "readable" / "commands.md"
    verdict_path = root / "readable" / "verdict.json"
    command_count = operator_feedback_cycle_count_from_commands(commands_path)
    verdict_payload: dict[str, Any] = {}
    if verdict_path.exists():
        try:
            parsed = json.loads(verdict_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                verdict_payload = parsed
        except json.JSONDecodeError:
            verdict_payload = {}
    summary_count_raw = verdict_payload.get("operator_feedback_cycles")
    if isinstance(summary_count_raw, int):
        summary_count = summary_count_raw
    elif isinstance(summary_count_raw, str) and summary_count_raw.isdigit():
        summary_count = int(summary_count_raw)
    else:
        summary_count = None
    attempted_count_raw = verdict_payload.get("operator_feedback_cycles_attempted", summary_count)
    if isinstance(attempted_count_raw, int):
        attempted_count = attempted_count_raw
    elif isinstance(attempted_count_raw, str) and attempted_count_raw.isdigit():
        attempted_count = int(attempted_count_raw)
    else:
        attempted_count = None
    status = "pass" if summary_count == command_count and attempted_count == command_count else "fail"
    failing_codes = []
    if summary_count != command_count or attempted_count != command_count:
        failing_codes.append("operator_feedback_cycle_counter_mismatch")
    return {
        "status": status,
        "commands_path": str(commands_path),
        "verdict_path": str(verdict_path),
        "command_operator_apply_cycles": command_count,
        "summary_operator_feedback_cycles": summary_count,
        "summary_operator_feedback_cycles_attempted": attempted_count,
        "failing_codes": failing_codes,
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _quality_eval_sort_key(path: Path) -> tuple[str, str]:
    payload = _read_json_file(path)
    evaluated_at = str(payload.get("evaluated_at") or "")
    return (evaluated_at, path.name)


def _artifact_quality_eval_files(root: Path) -> list[Path]:
    artifact_dir = root / "artifacts"
    if not artifact_dir.exists():
        return []
    files = sorted(dict.fromkeys(artifact_dir.glob("quality-eval*.json")))
    return sorted(files, key=_quality_eval_sort_key)


def _artifact_execution_files(root: Path) -> list[Path]:
    artifact_dir = root / "artifacts"
    files = sorted(artifact_dir.glob("qa-loop-execution*.json")) if artifact_dir.exists() else []
    if artifact_dir.exists():
        files.extend(sorted(artifact_dir.glob("operator_feedback.execution*.json")))
        files.extend(sorted(artifact_dir.glob("session-snapshot-final/artifacts/operator_feedback.execution*.json")))
    workdir_runtime = root / "workdir" / ".paper-orchestra"
    if workdir_runtime.exists():
        files.extend(sorted(workdir_runtime.glob("qa-loop-execution*.json")))
    return sorted(dict.fromkeys(files))


def _citation_review_hash_from_quality_eval(payload: dict[str, Any]) -> str | None:
    source = payload.get("source_artifacts") if isinstance(payload, dict) else {}
    value = source.get("citation_review_sha256") if isinstance(source, dict) else None
    if value is None:
        return None
    text = str(value)
    return text.split("sha256:", 1)[1] if text.startswith("sha256:") else text


def validate_fresh_smoke_lane_a_acceptance(evidence_root: str | Path) -> dict[str, Any]:
    """Validate the Lane-A smoke acceptance predicates from the strict review.

    P1: same-manuscript quality-eval failures must not report forward progress.
    P2: byte-identical operator attempts must be labelled as identical output or crash.
    P3: consecutive same-manuscript quality-eval artifacts must refer to the same
        citation-support review hash.
    """
    root = Path(evidence_root)
    failures: list[dict[str, Any]] = []
    quality_files = _artifact_quality_eval_files(root)
    quality_payloads = [(path, _read_json_file(path)) for path in quality_files]

    p1_checked = 0
    for path, payload in quality_payloads:
        regression = ((payload.get("cross_iteration") or {}).get("regression") or {}) if isinstance(payload, dict) else {}
        if not regression.get("same_manuscript_as_previous"):
            continue
        failing_codes = _failing_codes_from_quality_eval(payload)
        if not failing_codes:
            continue
        p1_checked += 1
        if regression.get("forward_progress") is not False:
            failures.append(
                {
                    "predicate": "P1",
                    "path": str(path),
                    "reason": "same manuscript with failing codes reported forward_progress != false",
                    "failing_codes": failing_codes,
                    "forward_progress": regression.get("forward_progress"),
                }
            )

    p2_checked = 0
    for path in _artifact_execution_files(root):
        payload = _read_json_file(path)
        base_sha = str(payload.get("manuscript_sha256_before") or "")
        if base_sha.startswith("sha256:"):
            base_sha = base_sha.split("sha256:", 1)[1]
        if not base_sha:
            continue
        for attempt in payload.get("attempts") or []:
            if not isinstance(attempt, dict):
                continue
            candidate_sha = str(attempt.get("candidate_sha256") or "")
            if candidate_sha.startswith("sha256:"):
                candidate_sha = candidate_sha.split("sha256:", 1)[1]
            if not candidate_sha or candidate_sha != base_sha:
                continue
            p2_checked += 1
            reasons = {str(reason) for reason in attempt.get("gate_reasons") or []}
            if not ({"executor_returned_identical_content", "executor_crashed"} & reasons):
                failures.append(
                    {
                        "predicate": "P2",
                        "path": str(path),
                        "attempt_index": attempt.get("attempt_index"),
                        "reason": "byte-identical candidate attempt lacks executor_returned_identical_content or executor_crashed",
                        "gate_reasons": sorted(reasons),
                    }
                )

    p3_checked = 0
    previous_path: Path | None = None
    previous_payload: dict[str, Any] | None = None
    for path, payload in quality_payloads:
        if previous_payload is not None and previous_payload.get("manuscript_hash") and payload.get("manuscript_hash") == previous_payload.get("manuscript_hash"):
            before_hash = _citation_review_hash_from_quality_eval(previous_payload)
            after_hash = _citation_review_hash_from_quality_eval(payload)
            if before_hash is None or after_hash is None:
                previous_path = path
                previous_payload = payload
                continue
            p3_checked += 1
            if before_hash != after_hash:
                failures.append(
                    {
                        "predicate": "P3",
                        "previous_path": str(previous_path),
                        "path": str(path),
                        "reason": "consecutive same-manuscript quality evals reference different citation-support review hashes",
                        "previous_citation_review_sha256": before_hash,
                        "citation_review_sha256": after_hash,
                    }
                )
        previous_path = path
        previous_payload = payload

    return {
        "schema_version": "fresh-smoke-lane-a-acceptance/1",
        "status": "pass" if not failures else "fail",
        "predicates": {
            "P1": {"checked": p1_checked, "description": "same-manuscript failures imply forward_progress=false"},
            "P2": {"checked": p2_checked, "description": "byte-identical attempts are labelled identical-output or crash"},
            "P3": {"checked": p3_checked, "description": "same-manuscript citation-support review identity is stable"},
        },
        "failing_codes": [] if not failures else ["fresh_smoke_lane_a_acceptance_failed"],
        "failures": failures,
    }


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
        },
    }
