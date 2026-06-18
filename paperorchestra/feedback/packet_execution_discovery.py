from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path, runtime_root


def _first_existing(*paths: str | Path | None) -> Path | None:
    for path in paths:
        if not path:
            continue
        candidate = Path(path).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _latest_human_needed_execution(cwd: str | Path | None) -> Path | None:
    executions = sorted(runtime_root(cwd).glob("qa-loop-execution.iter-*.json"))
    if not executions:
        return None
    latest = executions[-1]
    try:
        payload = read_json(latest)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("verdict") == "human_needed":
        return latest
    return None


def _latest_human_needed_operator_feedback_execution(cwd: str | Path | None) -> Path | None:
    path = artifact_path(cwd, "operator_feedback.execution.json")
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("verdict") == "human_needed":
        return path
    return None
