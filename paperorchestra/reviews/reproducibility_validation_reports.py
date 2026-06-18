from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility_artifacts import _file_sha256, _read_json_if_exists


def _current_validation_paths(state, session_artifact_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if state.artifacts.latest_validation_json:
        paths.append(Path(state.artifacts.latest_validation_json))
    elif session_artifact_dir is not None and session_artifact_dir.exists():
        for name in ("validation.refine.iter-*.json", "validation.sections.json", "validation.intro_related.json"):
            matches = sorted(session_artifact_dir.glob(name))
            if matches:
                paths.append(matches[-1])
                break
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def _validation_warning_reports(state, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    if session_artifact_dir is None or not session_artifact_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    expected_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    for path in _current_validation_paths(state, session_artifact_dir):
        payload = _read_json_if_exists(path)
        if not payload:
            continue
        if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
            continue
        warning_count = int(payload.get("warning_count") or 0)
        if warning_count <= 0:
            continue
        reports.append(
            {
                "path": str(path),
                "stage": payload.get("stage"),
                "warning_count": warning_count,
                "warning_summary": payload.get("warning_summary", []),
            }
        )
    return reports
