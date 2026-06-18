from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.citation_support_legacy_analysis import analyze_legacy_citation_support
from paperorchestra.loop_engine.quality.citation_support_legacy_result import (
    build_legacy_citation_support_result,
    legacy_stale_result,
)
from paperorchestra.loop_engine.quality.utils import _file_sha256


def _legacy_citation_support_check(
    cwd: str | Path | None,
    state: Any,
    path: Path,
    payload: dict[str, Any],
    *,
    quality_mode: str = "ralph",
) -> dict[str, Any]:
    del cwd  # Legacy payload validation only needs the state artifacts and review path.
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        return legacy_stale_result(path, payload, current_sha=current_sha)
    analysis = analyze_legacy_citation_support(state, payload, quality_mode=quality_mode)
    return build_legacy_citation_support_result(path, payload, analysis)
