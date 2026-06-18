from __future__ import annotations

from dataclasses import replace
from typing import Any

from paperorchestra.loop_engine.ralph.bridge_candidate_models import CandidateResolutionResult, PostActionState
from paperorchestra.loop_engine.ralph.bridge_records import build_restored_bridge_update


def baseline_candidate_result(state: PostActionState) -> CandidateResolutionResult:
    return CandidateResolutionResult(
        final_eval_path=state.eval_path,
        final_eval=state.eval_payload,
        final_plan_path=state.plan_path,
        final_plan=state.plan_payload,
        final_summary=state.summary,
        final_progress=state.progress,
        final_verification=state.verification,
        verdict=state.verdict,
    )


def apply_restored_current(
    result: CandidateResolutionResult,
    restored: dict[str, Any] | None,
) -> CandidateResolutionResult:
    if not restored:
        return result
    restored_update = build_restored_bridge_update(restored)
    updates = dict(result.execution_updates)
    updates.update(restored_update["execution_updates"])
    return replace(
        result,
        final_eval_path=restored_update["final_eval_path"],
        final_eval=restored_update["final_eval"],
        final_plan_path=restored_update["final_plan_path"],
        final_plan=restored_update["final_plan"],
        final_summary=restored_update["final_summary"],
        final_progress=restored_update["final_progress"],
        final_verification=restored_update["final_verification"],
        execution_updates=updates,
    )


def with_candidate_updates(result: CandidateResolutionResult, **updates: Any) -> CandidateResolutionResult:
    merged = dict(result.execution_updates)
    merged.update(updates)
    return replace(result, execution_updates=merged)
