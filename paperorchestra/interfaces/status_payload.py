from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.engine.plan_gate import check_plan_gate
from paperorchestra.manuscript.narrative_artifacts import planning_artifact_status
from paperorchestra.manuscript.skeleton import paper_skeleton_status


def build_session_status_payload(cwd: str | Path, *, include_recovery: bool = False) -> dict[str, Any]:
    payload = load_session(cwd).to_dict()
    if include_recovery:
        from paperorchestra.runtime.doctor import build_session_recovery_hint

        payload["session_recovery"] = build_session_recovery_hint(cwd)
    payload["plan_gate"] = check_plan_gate(cwd).to_dict()
    payload["planning_artifacts"] = _safe_status(lambda: planning_artifact_status(cwd))
    payload["paper_skeleton"] = _safe_status(lambda: paper_skeleton_status(cwd))
    return payload


def _safe_status(builder: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return builder()
    except Exception as exc:
        return {"status": "unknown", "error": str(exc)}


__all__ = ["build_session_status_payload"]
