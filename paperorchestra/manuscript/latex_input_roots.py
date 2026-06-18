from __future__ import annotations

from pathlib import Path


def _infer_project_root_from_source(source_path: Path) -> Path:
    for parent in source_path.parents:
        if parent.name == ".paper-orchestra":
            return parent.parent
    return source_path.parent


def _infer_run_root_from_source(source_path: Path) -> Path:
    for parent in source_path.parents:
        if parent.name == "artifacts":
            return parent.parent
    return source_path.parent
