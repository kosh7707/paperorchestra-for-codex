from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility_artifacts import _file_sha256, _read_json_if_exists

STRICT_FIGURE_WARNING_CODES = {
    "after_conclusion",
    "far_from_first_reference",
    "tail_clump",
    "wide_figure_mismatch",
}


def _strict_figure_review_issues(state: Any, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    expected_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    candidates: list[Path] = []
    if state.artifacts.latest_figure_placement_review_json:
        candidates.append(Path(state.artifacts.latest_figure_placement_review_json))
    if session_artifact_dir is not None:
        candidates.append(session_artifact_dir / "figure-placement-review.json")

    issues: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    found_figure_review = False
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen_paths or not path.exists():
            continue
        seen_paths.add(resolved)
        payload = _read_json_if_exists(path)
        if not payload:
            continue
        found_figure_review = True
        if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
            issues.append(
                {
                    "source": str(path),
                    "stage": "figure_placement",
                    "kind": "figure_placement_review_stale",
                    "code": "figure_placement_review_stale",
                    "message": "Figure placement review is missing or stale for the current manuscript.",
                    "severity": "error",
                }
            )
            continue
        issues.extend(_strict_figure_payload_issues(path, payload))
    if state.artifacts.paper_full_tex and expected_manuscript_sha and not found_figure_review:
        issues.append(
            {
                "source": None,
                "stage": "figure_placement",
                "kind": "figure_placement_review_missing",
                "code": "figure_placement_review_missing",
                "message": "Strict content gates require a current figure-placement review for the manuscript.",
                "severity": "error",
            }
        )
    return issues


def _strict_figure_payload_issues(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for failure in payload.get("failures") or []:
        if not isinstance(failure, dict):
            continue
        code = failure.get("code")
        if not code:
            continue
        issues.append(
            {
                "source": str(path),
                "stage": "figure_placement",
                "kind": "figure_placement_failure",
                "code": code,
                "message": failure.get("message"),
                "severity": "error",
            }
        )
    for warning in payload.get("warnings") or []:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        if code in STRICT_FIGURE_WARNING_CODES:
            issues.append(
                {
                    "source": str(path),
                    "stage": "figure_placement",
                    "kind": "figure_placement_warning",
                    "code": code,
                    "message": warning.get("message"),
                    "severity": "warning",
                }
            )
    return issues
