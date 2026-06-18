from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import artifact_path


def _reference_case_dir(cwd: str | Path | None, case_id: str) -> Path:
    return artifact_path(cwd, f"references/{case_id}/source.meta.json").parent


def _human_resolution_path(cwd: str | Path | None, case_id: str) -> Path:
    return _reference_case_dir(cwd, case_id) / "human-resolution.json"
