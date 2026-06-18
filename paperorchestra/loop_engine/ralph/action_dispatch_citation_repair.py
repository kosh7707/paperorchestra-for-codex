from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.action_dispatch_dependencies import _handler_dependency
from paperorchestra.loop_engine.ralph.action_dispatch_types import QaLoopActionDispatchContext, _QaLoopActionDispatchState
from paperorchestra.loop_engine.ralph.citation_candidate_preservation import (
    preserve_citation_candidate_for_approval as _preserve_citation_candidate_for_approval,
)
from paperorchestra.loop_engine.ralph.repair import repair_citation_claims as _repair_citation_claims
from paperorchestra.loop_engine.ralph.semantic_failure_payload import _citation_repair_failure_payload
from paperorchestra.loop_engine.ralph.state import _artifact_sha as _artifact_sha_real
from paperorchestra.loop_engine.ralph.state import guarded_replace_manuscript_text as _guarded_replace_manuscript_text


def _handle_citation_repair(
    code: str,
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
    state: _QaLoopActionDispatchState,
) -> bool:
    repair = _handler_dependency("repair_citation_claims", _repair_citation_claims)(
        context.cwd,
        context.provider,
        runtime_mode=context.runtime_mode,
        require_compile=context.require_compile,
        commit=False,
    )
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
        return False
    if context.paper_path and repair.get("candidate_path"):
        preserved_candidate_path = _handler_dependency(
            "preserve_citation_candidate_for_approval",
            _preserve_citation_candidate_for_approval,
        )(context.cwd, repair.get("candidate_path"))
        if preserved_candidate_path:
            repair = dict(repair)
            repair.setdefault("raw_candidate_path", str(repair.get("candidate_path")))
            repair["candidate_path"] = preserved_candidate_path
            repair["candidate_sha256"] = _handler_dependency("_artifact_sha", _artifact_sha_real)(preserved_candidate_path)
        state.citation_candidate_path = str(repair["candidate_path"])
        _handler_dependency("guarded_replace_manuscript_text", _guarded_replace_manuscript_text)(
            context.cwd,
            context.paper_path,
            Path(state.citation_candidate_path).read_text(encoding="utf-8"),
            reason="qa_loop_citation_candidate_for_validation",
            original_text=context.original_paper,
        )
        state.citation_candidate_applied = True
    execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
    return True
