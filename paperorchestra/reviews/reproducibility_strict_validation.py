from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility_artifacts import _file_sha256, _read_json_if_exists
from paperorchestra.reviews.reproducibility_validation_reports import _current_validation_paths

STRICT_VALIDATION_WARNING_CODES = {"unsupported_comparative_claim"}


def _strict_validation_report_issues(state: Any, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
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
            issues.extend(_strict_validation_warning_issues(path, payload))
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
    return issues


def _strict_validation_warning_issues(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
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
    return issues
