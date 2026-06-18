from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS, write_quality_eval, write_quality_loop_plan
from paperorchestra.loop_engine.ralph.state import SUPPORTED_HANDLER_CODES, _failing_codes, _qa_loop_step_command, _read_json


@dataclass(frozen=True)
class RalphBriefActionBuckets:
    actions: list[dict[str, Any]] = field(default_factory=list)
    executable_actions: list[dict[str, Any]] = field(default_factory=list)
    human_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RalphBriefContext:
    state: Any
    quality_mode: str
    max_iterations: int
    require_live_verification: bool
    accept_mixed_provenance: bool
    quality_eval_path: str | Path | None
    plan_path: str | Path | None
    quality_eval: dict[str, Any]
    plan: dict[str, Any]
    failing_codes: list[str]
    action_buckets: RalphBriefActionBuckets
    step_command: str


def build_ralph_brief_context(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    quality_eval_path: str | Path | None = None,
    plan_path: str | Path | None = None,
    _load_session_fn=load_session,
    _artifact_path_fn=artifact_path,
    _read_json_fn=_read_json,
    _write_quality_eval_fn=write_quality_eval,
    _write_quality_loop_plan_fn=write_quality_loop_plan,
    _step_command_fn=_qa_loop_step_command,
) -> RalphBriefContext:
    state = _load_session_fn(cwd)
    quality_eval_path, quality_eval = _load_or_write_quality_eval(
        cwd,
        quality_eval_path=quality_eval_path,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        artifact_path_fn=_artifact_path_fn,
        read_json_fn=_read_json_fn,
        write_quality_eval_fn=_write_quality_eval_fn,
    )
    plan_path, plan = _load_or_write_plan(
        cwd,
        plan_path=plan_path,
        quality_eval_path=quality_eval_path,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        read_json_fn=_read_json_fn,
        write_quality_loop_plan_fn=_write_quality_loop_plan_fn,
    )
    quality_eval_dict = quality_eval if isinstance(quality_eval, dict) else {}
    plan_dict = plan if isinstance(plan, dict) else {}
    return RalphBriefContext(
        state=state,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_path=quality_eval_path,
        plan_path=plan_path,
        quality_eval=quality_eval_dict,
        plan=plan_dict,
        failing_codes=_failing_codes(quality_eval_dict),
        action_buckets=_action_buckets(plan_dict.get("repair_actions", [])),
        step_command=_step_command_fn(
            quality_mode=quality_mode,
            max_iterations=max_iterations,
            require_live_verification=require_live_verification,
            accept_mixed_provenance=accept_mixed_provenance,
        ),
    )


def _load_or_write_quality_eval(
    cwd: str | Path | None,
    *,
    quality_eval_path: str | Path | None,
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    artifact_path_fn,
    read_json_fn,
    write_quality_eval_fn,
) -> tuple[str | Path | None, Any]:
    if quality_eval_path and Path(quality_eval_path).exists():
        return quality_eval_path, read_json_fn(quality_eval_path)
    _, quality_eval = write_quality_eval_fn(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
    )
    return artifact_path_fn(cwd, "quality-eval.json"), quality_eval


def _load_or_write_plan(
    cwd: str | Path | None,
    *,
    plan_path: str | Path | None,
    quality_eval_path: str | Path | None,
    require_live_verification: bool,
    quality_mode: str,
    max_iterations: int,
    accept_mixed_provenance: bool,
    read_json_fn,
    write_quality_loop_plan_fn,
) -> tuple[str | Path | None, Any]:
    if plan_path and Path(plan_path).exists():
        return plan_path, read_json_fn(plan_path)
    return write_quality_loop_plan_fn(
        cwd,
        require_live_verification=require_live_verification,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=quality_eval_path,
    )


def _action_buckets(actions: Any) -> RalphBriefActionBuckets:
    action_list = [action for action in actions if isinstance(action, dict)] if isinstance(actions, list) else []
    executable_actions = [
        action
        for action in action_list
        if action.get("automation") in {"automatic", "semi_auto"}
        and str(action.get("code")) in SUPPORTED_HANDLER_CODES
    ]
    human_actions = [action for action in action_list if action.get("automation") == "human_needed"]
    return RalphBriefActionBuckets(
        actions=action_list,
        executable_actions=executable_actions,
        human_actions=human_actions,
    )
