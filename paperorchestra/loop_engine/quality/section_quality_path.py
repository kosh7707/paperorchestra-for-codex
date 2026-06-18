from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import artifact_path


def _section_review_path(cwd: str | Path | None, state) -> Path:
    candidates: list[Path] = []
    latest = getattr(state.artifacts, "latest_section_review_json", None)
    if latest:
        candidates.append(Path(latest))
    if state.artifacts.paper_full_tex:
        candidates.append(Path(state.artifacts.paper_full_tex).resolve().parent / "section_review.json")
    candidates.append(artifact_path(cwd, "section_review.json"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
