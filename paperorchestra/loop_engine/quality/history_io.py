from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.session import runtime_root
from paperorchestra.loop_engine.quality.policy import HISTORY_FILENAME


def quality_loop_history_path(cwd: str | Path | None) -> Path:
    return runtime_root(cwd) / HISTORY_FILENAME


def _read_quality_history(cwd: str | Path | None) -> list[dict[str, Any]]:
    path = quality_loop_history_path(cwd)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def operator_feedback_cycle_count(cwd: str | Path | None, session_id: str | None = None) -> int:
    if session_id is None:
        current_session = runtime_root(cwd) / "current_session.txt"
        if current_session.exists():
            session_id = current_session.read_text(encoding="utf-8").strip() or None
    return sum(
        1
        for entry in _read_quality_history(cwd)
        if entry.get("event_type") == "operator_feedback_cycle"
        and (session_id is None or entry.get("session_id") == session_id)
    )
