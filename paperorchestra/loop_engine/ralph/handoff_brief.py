from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS, write_quality_eval, write_quality_loop_plan
from paperorchestra.loop_engine.ralph.handoff_brief_context import build_ralph_brief_context
from paperorchestra.loop_engine.ralph.handoff_brief_renderer import render_qa_loop_brief
from paperorchestra.loop_engine.ralph.state import QA_LOOP_BRIEF_FILENAME, _qa_loop_step_command, _read_json


def build_qa_loop_brief(
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
) -> str:
    context = build_ralph_brief_context(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_path=quality_eval_path,
        plan_path=plan_path,
        _load_session_fn=_load_session_fn,
        _artifact_path_fn=_artifact_path_fn,
        _read_json_fn=_read_json_fn,
        _write_quality_eval_fn=_write_quality_eval_fn,
        _write_quality_loop_plan_fn=_write_quality_loop_plan_fn,
        _step_command_fn=_step_command_fn,
    )
    return render_qa_loop_brief(context)


def write_qa_loop_brief(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    _artifact_path_fn=artifact_path,
    _build_brief_fn=build_qa_loop_brief,
    **kwargs: Any,
) -> tuple[Path, str]:
    text = _build_brief_fn(cwd, **kwargs)
    path = Path(output_path).resolve() if output_path else _artifact_path_fn(cwd, QA_LOOP_BRIEF_FILENAME)
    path.write_text(text, encoding="utf-8")
    return path, text
