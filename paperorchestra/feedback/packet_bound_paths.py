from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json
from paperorchestra.feedback import packet_bindings as _packet_bindings
from paperorchestra.feedback.packet_execution_discovery import _first_existing


def _current_bound_execution_path(path: Path | None, *, role: str, current_manuscript_sha256: str | None) -> Path | None:
    if path is None or not current_manuscript_sha256:
        return path
    try:
        payload = read_json(path)
    except Exception:
        return path
    if not isinstance(payload, dict):
        return path
    bound_sha = _packet_bindings._artifact_bound_manuscript_sha(role, payload)
    if role == "figure_placement_review" and bound_sha is None:
        return None
    if bound_sha is not None and bound_sha != current_manuscript_sha256:
        return None
    return path


def _first_current_bound_existing(
    role: str,
    current_manuscript_sha256: str | None,
    *paths: str | Path | None,
) -> Path | None:
    for path in paths:
        candidate = _first_existing(path)
        if candidate is None:
            continue
        current = _current_bound_execution_path(
            candidate,
            role=role,
            current_manuscript_sha256=current_manuscript_sha256,
        )
        if current is not None:
            return current
    return None
