from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.loop import write_quality_eval, write_quality_loop_plan
from paperorchestra.loop_engine.ralph.bridge_actions import _executable_actions, _unsupported_executable_actions
from paperorchestra.loop_engine.ralph.bridge_records import build_initial_execution_record
from paperorchestra.loop_engine.ralph.inputs import (
    _load_explicit_qa_loop_plan,
    _load_explicit_quality_eval,
    _quality_eval_path_from_plan,
    _stage_explicit_citation_support_review,
    _validate_plan_quality_eval_identity,
)
from paperorchestra.loop_engine.ralph.state import _citation_summary


@dataclass(frozen=True)
class QaLoopPreflight:
    before_eval_path: str | Path
    before_eval: dict[str, Any]
    before_plan_path: str | Path
    before_summary: dict[str, Any]
    initial_verdict: str
    execution: dict[str, Any]
    actions: list[dict[str, Any]]
    unsupported_actions: list[dict[str, Any]]


def prepare_qa_loop_preflight(
    *,
    cwd: str | Path | None,
    started_at: str,
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    accept_mixed_provenance: bool,
    quality_eval_input_path: str | Path | None,
    qa_loop_plan_input_path: str | Path | None,
    citation_support_review_path: str | Path | None,
) -> QaLoopPreflight:
    explicit_citation_support_path = _stage_explicit_citation_support_review(cwd, citation_support_review_path)
    if qa_loop_plan_input_path:
        before_plan_path = Path(qa_loop_plan_input_path).resolve()
        before_plan = _load_explicit_qa_loop_plan(cwd, before_plan_path)
        effective_eval_input_path = quality_eval_input_path or _quality_eval_path_from_plan(before_plan)
        if not effective_eval_input_path:
            raise ValueError(f"qa-loop-plan input does not identify a quality-eval artifact: {before_plan_path}")
        before_eval_path, before_eval = _load_explicit_quality_eval(cwd, effective_eval_input_path)
        _validate_plan_quality_eval_identity(before_plan, before_eval_path)
    else:
        if quality_eval_input_path:
            before_eval_path, before_eval = _load_explicit_quality_eval(cwd, quality_eval_input_path)
        else:
            before_eval_path, before_eval = write_quality_eval(
                cwd,
                require_live_verification=require_live_verification,
                quality_mode=quality_mode,
                max_iterations=max_iterations,
            )
        before_plan_path, before_plan = write_quality_loop_plan(
            cwd,
            require_live_verification=require_live_verification,
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            accept_mixed_provenance=accept_mixed_provenance,
            quality_eval_input_path=before_eval_path,
        )
    before_summary = _citation_summary(cwd)
    initial_verdict = str(before_plan.get("verdict"))
    execution = build_initial_execution_record(
        cwd=cwd,
        started_at=started_at,
        before_eval_path=before_eval_path,
        before_plan_path=before_plan_path,
        explicit_citation_support_path=explicit_citation_support_path,
        before_eval=before_eval,
        before_summary=before_summary,
    )
    return QaLoopPreflight(
        before_eval_path=before_eval_path,
        before_eval=before_eval,
        before_plan_path=before_plan_path,
        before_summary=before_summary,
        initial_verdict=initial_verdict,
        execution=execution,
        actions=_executable_actions(before_plan),
        unsupported_actions=_unsupported_executable_actions(before_plan),
    )
