from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.ralph.state import _read_json


def _citation_integrity_audit(cwd: str | Path | None) -> dict[str, Any]:
    return _optional_artifact_json(cwd, "citation_integrity.audit.json")


def _citation_support_review(cwd: str | Path | None) -> dict[str, Any]:
    return _optional_artifact_json(cwd, "citation_support_review.json")


def _quality_eval_artifact(cwd: str | Path | None) -> dict[str, Any]:
    return _optional_artifact_json(cwd, "quality-eval.json")


def _optional_artifact_json(cwd: str | Path | None, name: str) -> dict[str, Any]:
    try:
        payload = _read_json(artifact_path(cwd, name))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
