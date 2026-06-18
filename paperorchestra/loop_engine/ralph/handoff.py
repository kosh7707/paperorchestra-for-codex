from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.loop_engine.quality.loop import DEFAULT_MAX_ITERATIONS, write_quality_eval, write_quality_loop_plan
from paperorchestra.loop_engine.ralph.handoff_brief import build_qa_loop_brief as _build_qa_loop_brief_impl
from paperorchestra.loop_engine.ralph.handoff_start_payload import (
    build_ralph_start_payload as _build_ralph_start_payload_impl,
    launch_omx_ralph,
)
from paperorchestra.loop_engine.ralph.state import (
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_BRIEF_FILENAME,
    QA_LOOP_HANDOFF_FILENAME,
    SUPPORTED_HANDLER_CODES,
    _failing_codes,
    _qa_loop_step_command,
    _read_json,
)


def build_qa_loop_brief(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    quality_eval_path: str | Path | None = None,
    plan_path: str | Path | None = None,
) -> str:
    return _build_qa_loop_brief_impl(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_path=quality_eval_path,
        plan_path=plan_path,
        _load_session_fn=load_session,
        _artifact_path_fn=artifact_path,
        _read_json_fn=_read_json,
        _write_quality_eval_fn=write_quality_eval,
        _write_quality_loop_plan_fn=write_quality_loop_plan,
        _step_command_fn=_qa_loop_step_command,
    )


def write_qa_loop_brief(cwd: str | Path | None, output_path: str | Path | None = None, **kwargs: Any) -> tuple[Path, str]:
    text = build_qa_loop_brief(cwd, **kwargs)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, QA_LOOP_BRIEF_FILENAME)
    path.write_text(text, encoding="utf-8")
    return path, text


def build_ralph_start_payload(
    cwd: str | Path | None,
    *,
    quality_mode: str = "claim_safe",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    output_path: str | Path | None = None,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    evidence_root: str | Path | None = None,
) -> dict[str, Any]:
    return _build_ralph_start_payload_impl(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        output_path=output_path,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        evidence_root=evidence_root,
        _write_brief_fn=write_qa_loop_brief,
        _load_session_fn=load_session,
        _write_json_fn=write_json,
        _artifact_path_fn=artifact_path,
        _step_command_fn=_qa_loop_step_command,
    )


__all__ = [
    "Any",
    "DEFAULT_MAX_ITERATIONS",
    "OMX_TMUX_INJECT_MARKER",
    "OMX_TMUX_INJECT_PROMPT",
    "Path",
    "QA_LOOP_BRIEF_FILENAME",
    "QA_LOOP_HANDOFF_FILENAME",
    "SUPPORTED_HANDLER_CODES",
    "_failing_codes",
    "_qa_loop_step_command",
    "_read_json",
    "artifact_path",
    "build_qa_loop_brief",
    "build_ralph_start_payload",
    "launch_omx_ralph",
    "load_session",
    "shlex",
    "subprocess",
    "write_json",
    "write_qa_loop_brief",
    "write_quality_eval",
    "write_quality_loop_plan",
]
