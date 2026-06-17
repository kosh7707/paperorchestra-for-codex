from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.state import _read_json


def _validation_failing_codes_from_repair(repair: dict[str, Any]) -> list[str]:
    validation = repair.get("validation") if isinstance(repair.get("validation"), dict) else {}
    path = validation.get("path") if isinstance(validation, dict) else None
    payload = _read_json(path) if path else None
    issues = payload.get("issues") if isinstance(payload, dict) and isinstance(payload.get("issues"), list) else []
    codes = [str(issue.get("code")) for issue in issues if isinstance(issue, dict) and issue.get("code")]
    if not codes and isinstance(validation, dict) and validation.get("ok") is False:
        codes.append("validation_failed")
    return sorted(dict.fromkeys(codes))


def _semantic_metric_count(metrics: dict[str, Any], key: str) -> int | None:
    value = metrics.get(key) if isinstance(metrics, dict) else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _semantic_recheck_gate_summary(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(payload, dict):
        return None, []
    summary: dict[str, Any] = {"status": str(payload.get("status") or "unknown")}
    blockers: list[str] = []

    def _lane(name: str, count_key: str, blocker: str) -> dict[str, Any] | None:
        lane = payload.get(name)
        if not isinstance(lane, dict):
            return None
        before = lane.get("before") if isinstance(lane.get("before"), dict) else {}
        after = lane.get("after") if isinstance(lane.get("after"), dict) else {}
        targeted = bool(lane.get("targeted"))
        improved = bool(lane.get("improved"))
        if targeted and not improved:
            blockers.append(blocker)
        compact: dict[str, Any] = {
            "targeted": targeted,
            "improved": improved,
            "before_count": _semantic_metric_count(before, count_key),
            "after_count": _semantic_metric_count(after, count_key),
        }
        if lane.get("baseline_source"):
            compact["baseline_source"] = lane.get("baseline_source")
        if lane.get("path"):
            compact["path"] = lane.get("path")
        if lane.get("sha256"):
            compact["sha256"] = lane.get("sha256")
        return compact

    citation = _lane("citation_integrity", "target_issue_count", "citation_integrity_not_improved")
    high_risk = _lane("high_risk_claim_sweep", "item_count", "high_risk_claim_sweep_not_improved")
    if citation is not None:
        summary["citation_integrity"] = citation
    if high_risk is not None:
        summary["high_risk_claim_sweep"] = high_risk
    return summary, sorted(dict.fromkeys(blockers))


def _citation_repair_failure_payload(code: str, repair: dict[str, Any]) -> dict[str, Any]:
    validation = repair.get("validation") if isinstance(repair.get("validation"), dict) else {}
    validation_codes = _validation_failing_codes_from_repair(repair)
    semantic_summary, semantic_blockers = _semantic_recheck_gate_summary(
        repair.get("semantic_recheck") if isinstance(repair.get("semantic_recheck"), dict) else {}
    )
    next_steps = [
        "Inspect validation failing codes before retrying citation repair.",
        "Refresh citation support evidence or weaken/delete unsupported claims.",
        "Rerun paperorchestra qa-loop --quality-mode claim_safe after targeted changes.",
    ]
    if str(repair.get("reason") or "") == "semantic_recheck_failed":
        next_steps = [
            "Inspect semantic_recheck blockers before retrying citation repair.",
            "Use the semantic recheck artifacts to identify whether citation integrity or high-risk claim sweep failed to improve.",
            "Weaken, split, or delete unsupported claims before rerunning paperorchestra qa-loop --quality-mode claim_safe.",
        ]
    payload = {
        "code": code,
        "handler": "repair_citation_claims",
        "reason": str(repair.get("reason") or "repair_not_accepted"),
        "issue_count": repair.get("issue_count"),
        "claim_safety_issue_count": repair.get("claim_safety_issue_count"),
        "candidate_path": repair.get("candidate_path"),
        "validation": {
            "path": validation.get("path") if isinstance(validation, dict) else None,
            "ok": validation.get("ok") if isinstance(validation, dict) else None,
            "blocking_issue_count": validation.get("blocking_issue_count") if isinstance(validation, dict) else None,
            "failing_codes": validation_codes,
        },
        "semantic_recheck_blockers": semantic_blockers,
        "next_steps": next_steps,
    }
    if semantic_summary is not None:
        payload["semantic_recheck"] = semantic_summary
    return payload


