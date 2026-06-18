from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session, save_session


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
