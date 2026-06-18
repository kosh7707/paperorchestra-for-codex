from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session, runtime_root, save_session
from paperorchestra.loop_engine.ralph.commands import (
    EXIT_CODES,
    MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME,
    NON_SUPPORTED_CITATION_STATUSES,
    OMX_TMUX_INJECT_MARKER,
    OMX_TMUX_INJECT_PROMPT,
    QA_LOOP_BRIEF_FILENAME,
    QA_LOOP_EXECUTION_SCHEMA_VERSION,
    QA_LOOP_HANDOFF_FILENAME,
    SUPPORTED_HANDLER_CODES,
    TERMINAL_VERDICTS,
    _qa_loop_step_command,
    qa_loop_exit_code,
)
from paperorchestra.loop_engine.ralph.io_files import (
    _artifact_sha,
    _file_content_snapshot,
    _read_json,
    _restore_file_content_snapshot,
    _text_sha256,
    atomic_write_text,
)
from paperorchestra.loop_engine.ralph.io_manuscript_write import (
    _candidate_write_marker_path,
    clear_pending_manuscript_write,
    guarded_replace_manuscript_text,
    recover_pending_manuscript_write,
)
from paperorchestra.loop_engine.ralph.progress import (
    _citation_issue_count,
    _citation_summary,
    _failing_codes,
    _manuscript_hash,
    compute_progress_delta,
    quality_eval_status,
)


@dataclass(frozen=True)
class StepResult:
    path: Path
    payload: dict[str, Any]
    exit_code: int


def _next_execution_path(cwd: str | Path | None) -> tuple[int, Path]:
    root = runtime_root(cwd)
    existing = sorted(root.glob("qa-loop-execution.iter-*.json"))
    index = len(existing) + 1
    return index, root / f"qa-loop-execution.iter-{index:02d}.json"


def _session_mutation_snapshot(state) -> dict[str, Any]:
    return {
        "latest_validation_json": state.artifacts.latest_validation_json,
        "latest_compile_report_json": state.artifacts.latest_compile_report_json,
        "compiled_pdf": state.artifacts.compiled_pdf,
        "active_artifact": state.active_artifact,
        "current_phase": state.current_phase,
        "notes": list(state.notes),
    }


def _restore_session_mutation_snapshot(cwd: str | Path | None, snapshot: dict[str, Any]) -> None:
    state = load_session(cwd)
    state.artifacts.latest_validation_json = snapshot.get("latest_validation_json")
    state.artifacts.latest_compile_report_json = snapshot.get("latest_compile_report_json")
    state.artifacts.compiled_pdf = snapshot.get("compiled_pdf")
    state.active_artifact = snapshot.get("active_artifact")
    state.current_phase = snapshot.get("current_phase")
    state.notes = list(snapshot.get("notes") or [])
    save_session(cwd, state)
