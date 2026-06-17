from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility_artifacts import (
    _file_sha256,
    _read_json_if_exists,
)


STRICT_VALIDATION_WARNING_CODES = {"unsupported_comparative_claim"}


STRICT_FIGURE_WARNING_CODES = {
    "after_conclusion",
    "far_from_first_reference",
    "tail_clump",
    "wide_figure_mismatch",
}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _strict_content_gates_enabled() -> bool:
    return _env_flag("PAPERO_STRICT_CONTENT_GATES")


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


def _strict_content_gate_issues(state, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    found_validation_report = False
    if session_artifact_dir is not None and session_artifact_dir.exists():
        for path in _current_validation_paths(state, session_artifact_dir):
            payload = _read_json_if_exists(path)
            if not payload:
                continue
            found_validation_report = True
            if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
                issues.append(
                    {
                        "source": str(path),
                        "stage": payload.get("stage"),
                        "kind": "validation_report_stale",
                        "code": "validation_report_stale",
                        "message": "Current validation report is missing or stale for the current manuscript.",
                        "severity": "error",
                    }
                )
                continue
            for issue in payload.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                code = issue.get("code")
                if code in STRICT_VALIDATION_WARNING_CODES:
                    issues.append(
                        {
                            "source": str(path),
                            "stage": payload.get("stage"),
                            "kind": "validation_warning",
                            "code": code,
                            "message": issue.get("message"),
                            "severity": issue.get("severity"),
                        }
                    )
    if state.artifacts.paper_full_tex and expected_manuscript_sha and not found_validation_report:
        issues.append(
            {
                "source": None,
                "stage": "validation",
                "kind": "validation_report_missing",
                "code": "validation_report_missing",
                "message": "Strict content gates require a current validation report for the manuscript.",
                "severity": "error",
            }
        )

    figure_review_candidates: list[Path] = []
    if state.artifacts.latest_figure_placement_review_json:
        figure_review_candidates.append(Path(state.artifacts.latest_figure_placement_review_json))
    if session_artifact_dir is not None:
        figure_review_candidates.append(session_artifact_dir / "figure-placement-review.json")

    seen_paths: set[Path] = set()
    found_figure_review = False
    for path in figure_review_candidates:
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
