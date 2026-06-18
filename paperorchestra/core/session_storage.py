from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from paperorchestra.core.models import SessionState, utc_now_iso
from paperorchestra.core.session_paths import session_path

NOTES_RETAIN_COUNT = 20
_SESSION_IO_LOCK = threading.RLock()


def load_session(cwd: str | Path | None, session_id: str | None = None) -> SessionState:
    path = session_path(cwd, session_id)
    if not path.exists():
        raise FileNotFoundError(f"Missing session file: {path}")
    with _SESSION_IO_LOCK:
        return SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_session(cwd: str | Path | None, state: SessionState) -> Path:
    path = session_path(cwd, state.session_id)
    _retain_recent_notes(state)
    state.updated_at = utc_now_iso()
    with _SESSION_IO_LOCK:
        _merge_existing_runtime_fields(path, state)
        tmp_path = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
        tmp_path.write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    return path


def _retain_recent_notes(state: SessionState) -> None:
    if len(state.notes) <= NOTES_RETAIN_COUNT:
        return
    overflow = state.notes[:-NOTES_RETAIN_COUNT]
    state.notes_archive.extend(overflow)
    state.notes = state.notes[-NOTES_RETAIN_COUNT:]


def _merge_existing_runtime_fields(path: Path, state: SessionState) -> None:
    existing = _read_existing_state(path)
    if existing is None:
        return
    for field_name in ("latest_prompt_trace_dir", "latest_provider_identity_json"):
        incoming_value = getattr(state.artifacts, field_name)
        existing_value = getattr(existing.artifacts, field_name)
        if incoming_value is None:
            setattr(state.artifacts, field_name, existing_value)
            continue
        if existing_value is None:
            continue
        if _existing_artifact_is_newer(existing_value, incoming_value):
            setattr(state.artifacts, field_name, existing_value)
    if state.latest_provider_name is None:
        state.latest_provider_name = existing.latest_provider_name
    if state.latest_runtime_mode is None:
        state.latest_runtime_mode = existing.latest_runtime_mode


def _read_existing_state(path: Path) -> SessionState | None:
    if not path.exists():
        return None
    try:
        return SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _existing_artifact_is_newer(existing_value: str, incoming_value: str) -> bool:
    existing_path = Path(existing_value)
    incoming_path = Path(incoming_value)
    return existing_path.exists() and (
        not incoming_path.exists() or existing_path.stat().st_mtime > incoming_path.stat().st_mtime
    )
