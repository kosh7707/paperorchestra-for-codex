from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json


def _load_registry_entries(registry_path: str | Path | None) -> tuple[str | None, list[dict[str, Any]]]:
    if not registry_path:
        return "missing", []
    candidate = Path(registry_path)
    if not candidate.exists():
        return "missing", []
    try:
        payload = read_json(candidate)
    except Exception:
        return "unreadable", []
    if not isinstance(payload, list):
        return "malformed", []
    return None, [item for item in payload if isinstance(item, dict)]
