from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.reviews.source_support import build_source_backed_citation_cases
from .citation_support_legacy import _legacy_citation_support_check
from .citation_support_v3 import _citation_support_check_v3
from .utils import _file_sha256, _read_json_if_exists


def _citation_support_path(cwd: str | Path | None, state) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent / "citation_support_review.json"
    return artifact_path(cwd, "citation_support_review.json")


def _citation_support_check(cwd: str | Path | None, state, *, quality_mode: str = "ralph") -> dict[str, Any]:
    path = _citation_support_path(cwd, state)
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {"status": "fail", "path": str(path), "failing_codes": ["citation_support_review_missing"], "summary": None}
    if payload.get("schema") == "citation-support-review/3":
        return _citation_support_check_v3(
            cwd,
            state,
            path,
            payload,
            quality_mode=quality_mode,
            case_builder=build_source_backed_citation_cases,
        )
    return _legacy_citation_support_check(cwd, state, path, payload, quality_mode=quality_mode)


def ensure_final_citation_review_bound_to_quality_eval(quality_eval_path: str | Path, final_review_path: str | Path) -> dict[str, Any]:
    """Validate that a surfaced final citation review is the gate-of-record artifact."""
    quality_eval = _read_json_if_exists(quality_eval_path)
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval, dict) else {}
    expected_sha = source_artifacts.get("citation_review_sha256") if isinstance(source_artifacts, dict) else None
    actual_sha = _file_sha256(final_review_path)
    if expected_sha and str(expected_sha).startswith("sha256:"):
        expected_sha = str(expected_sha).split("sha256:", 1)[1]
    if actual_sha and str(actual_sha).startswith("sha256:"):
        actual_sha = str(actual_sha).split("sha256:", 1)[1]
    if not expected_sha:
        raise ValueError("quality-eval source_artifacts.citation_review_sha256 is missing")
    if not actual_sha:
        raise ValueError(f"final citation review does not exist or is unreadable: {final_review_path}")
    if str(expected_sha) != str(actual_sha):
        raise ValueError(
            "final citation review is not bound to gate-of-record citation review "
            f"(expected sha256:{expected_sha}, actual sha256:{actual_sha})"
        )
    return {
        "status": "pass",
        "quality_eval_path": str(quality_eval_path),
        "final_review_path": str(final_review_path),
        "citation_review_sha256": str(actual_sha),
    }
