from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


def _loaded_section_review(path: Path) -> dict[str, Any] | None:
    payload = _read_json_if_exists(path)
    return payload if isinstance(payload, dict) else None


def _section_review_trust_failure(
    *,
    path: Path,
    payload: dict[str, Any] | None,
    current_sha: str | None,
) -> dict[str, Any] | None:
    if payload is None:
        return _base_section_failure(path, "section_review_missing", overall=None)
    if payload.get("schema_version") != "section-review/1" or not payload.get("manuscript_sha256"):
        return _base_section_failure(
            path,
            "section_review_legacy_untrusted",
            overall=payload.get("overall_section_score"),
            current_sha=current_sha,
            actual_sha=payload.get("manuscript_sha256"),
        )
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        return _base_section_failure(
            path,
            "section_review_stale",
            overall=payload.get("overall_section_score"),
            current_sha=current_sha,
            actual_sha=payload.get("manuscript_sha256"),
        )
    return None


def _current_manuscript_sha(state) -> str | None:
    return _file_sha256(state.artifacts.paper_full_tex)


def _base_section_failure(
    path: Path,
    code: str,
    *,
    overall: Any,
    current_sha: str | None = None,
    actual_sha: Any = None,
) -> dict[str, Any]:
    payload = {
        "status": "fail",
        "path": str(path),
        "failing_codes": [code],
        "overall_section_score": overall,
        "low_sections": [],
        "sections_with_required_fixes": [],
    }
    if current_sha is not None or actual_sha is not None:
        payload["expected_manuscript_sha256"] = current_sha
        payload["actual_manuscript_sha256"] = actual_sha
    return payload
