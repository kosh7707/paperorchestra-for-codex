from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.ralph.action_dispatch_types import (
    QaLoopActionDispatchContext,
    _QaLoopActionDispatchState,
)
from paperorchestra.loop_engine.ralph.repair import repair_citation_claims
from paperorchestra.loop_engine.ralph.semantic_gate_summary import _semantic_recheck_gate_summary
from paperorchestra.loop_engine.ralph.semantic_validation import _validation_failing_codes_from_repair
from paperorchestra.loop_engine.ralph.state import _artifact_sha, guarded_replace_manuscript_text

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


def preserve_citation_candidate_for_approval(
    cwd: str | Path | None,
    candidate_path: str | Path | None,
) -> str | None:
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


def citation_repair_failure_payload(code: str, repair: dict[str, Any]) -> dict[str, Any]:
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


def handle_citation_repair(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    repair = repair_citation_claims(
        context.cwd,
        context.provider,
        runtime_mode=context.runtime_mode,
        require_compile=context.require_compile,
        commit=False,
    )
    if not repair.get("accepted"):
        failure = citation_repair_failure_payload(code, repair)
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
        return False
    if context.paper_path and repair.get("candidate_path"):
        preserved_candidate_path = preserve_citation_candidate_for_approval(context.cwd, repair.get("candidate_path"))
        if preserved_candidate_path:
            repair = dict(repair)
            repair.setdefault("raw_candidate_path", str(repair.get("candidate_path")))
            repair["candidate_path"] = preserved_candidate_path
            repair["candidate_sha256"] = _artifact_sha(preserved_candidate_path)
        state.citation_candidate_path = str(repair["candidate_path"])
        guarded_replace_manuscript_text(
            context.cwd,
            context.paper_path,
            Path(state.citation_candidate_path).read_text(encoding="utf-8"),
            reason="qa_loop_citation_candidate_for_validation",
            original_text=context.original_paper,
        )
        state.citation_candidate_applied = True
    execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
    return True
