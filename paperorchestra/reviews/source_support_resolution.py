from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.source_support_resolution_actions import _apply_resolution_action
from paperorchestra.reviews.source_support_resolution_invalid import _mark_invalid_human_resolution
from paperorchestra.reviews.source_support_resolution_load import _load_human_resolution
from paperorchestra.reviews.source_support_resolution_paths import _human_resolution_path, _reference_case_dir


def _apply_human_resolution(cwd: str | Path | None, case: dict[str, Any], citation_map: dict[str, Any]) -> bool:
    """Apply a per-case human citation resolution.

    Returns True when evidence resolution must ignore pre-existing case-local
    source artifacts so stale source.txt/pdf/html cannot mask a human-provided
    URL or replacement citation.
    """

    resolution = _load_human_resolution(cwd, case)
    if resolution is None:
        return False
    if resolution.get("status") == "invalid":
        _mark_invalid_human_resolution(case, resolution)
        return False
    return _apply_resolution_action(case, resolution, citation_map)


__all__ = [
    "_apply_human_resolution",
    "_human_resolution_path",
    "_load_human_resolution",
    "_mark_invalid_human_resolution",
    "_reference_case_dir",
]
