from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.ralph.semantic_gate_summary import _semantic_recheck_gate_summary
from paperorchestra.loop_engine.ralph.semantic_validation import _validation_failing_codes_from_repair

_VALIDATION_FAILURE_NEXT_STEPS = [
    "Inspect validation failing codes before retrying citation repair.",
    "Refresh citation support evidence or weaken/delete unsupported claims.",
    "Rerun paperorchestra qa-loop --quality-mode claim_safe after targeted changes.",
]
_SEMANTIC_RECHECK_FAILURE_NEXT_STEPS = [
    "Inspect semantic_recheck blockers before retrying citation repair.",
    "Use the semantic recheck artifacts to identify whether citation integrity or high-risk claim sweep failed to improve.",
    "Weaken, split, or delete unsupported claims before rerunning paperorchestra qa-loop --quality-mode claim_safe.",
]


def _citation_repair_failure_payload(code: str, repair: dict[str, Any]) -> dict[str, Any]:
    validation = repair.get("validation") if isinstance(repair.get("validation"), dict) else {}
    semantic_summary, semantic_blockers = _semantic_recheck_gate_summary(
        repair.get("semantic_recheck") if isinstance(repair.get("semantic_recheck"), dict) else {}
    )
    payload = {
        "code": code,
        "handler": "repair_citation_claims",
        "reason": str(repair.get("reason") or "repair_not_accepted"),
        "issue_count": repair.get("issue_count"),
        "claim_safety_issue_count": repair.get("claim_safety_issue_count"),
        "candidate_path": repair.get("candidate_path"),
        "validation": _validation_payload(validation, repair),
        "semantic_recheck_blockers": semantic_blockers,
        "next_steps": _next_steps_for_repair(repair),
    }
    if semantic_summary is not None:
        payload["semantic_recheck"] = semantic_summary
    return payload


def _validation_payload(validation: Any, repair: dict[str, Any]) -> dict[str, Any]:
    validation = validation if isinstance(validation, dict) else {}
    return {
        "path": validation.get("path"),
        "ok": validation.get("ok"),
        "blocking_issue_count": validation.get("blocking_issue_count"),
        "failing_codes": _validation_failing_codes_from_repair(repair),
    }


def _next_steps_for_repair(repair: dict[str, Any]) -> list[str]:
    if str(repair.get("reason") or "") == "semantic_recheck_failed":
        return list(_SEMANTIC_RECHECK_FAILURE_NEXT_STEPS)
    return list(_VALIDATION_FAILURE_NEXT_STEPS)
