from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json


def _session_artifact_dir(state) -> Path | None:
    for candidate in [state.artifacts.paper_full_tex, state.artifacts.candidate_papers_json]:
        if candidate and Path(candidate).exists():
            return Path(candidate).resolve().parent
    return None


def _read_existing_json(path: str | Path | None, default: Any = None) -> Any:
    return read_json(path) if path and Path(path).exists() else default
