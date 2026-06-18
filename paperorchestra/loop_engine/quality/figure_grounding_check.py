from __future__ import annotations

from typing import Any

from paperorchestra.loop_engine.quality.figure_grounding_issues import figure_grounding_issue_figures
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


def _figure_grounding_check(state: Any) -> dict[str, Any]:
    path = state.artifacts.latest_figure_placement_review_json
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "status": "skipped",
            "reason": "figure_placement_review_missing_or_unreadable",
            "failing_codes": [],
            "warning_codes": [],
        }
    expected_sha = _file_sha256(getattr(state.artifacts, "paper_full_tex", None))
    actual_sha = _payload_manuscript_sha(payload)
    artifact_status = str(payload.get("status") or "unknown").strip().lower()
    if expected_sha and not actual_sha:
        return _unbound_result(path, expected_sha, artifact_status)
    if expected_sha and actual_sha != expected_sha:
        return _stale_result(path, expected_sha, actual_sha, artifact_status)
    return _bound_result(path, payload, artifact_status)


def _payload_manuscript_sha(payload: dict[str, Any]) -> str:
    actual = str(payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256") or "").strip()
    return actual.split("sha256:", 1)[1] if actual.startswith("sha256:") else actual


def _unbound_result(path: Any, expected_sha: str, artifact_status: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "failing_codes": ["figure_placement_review_unbound"],
        "warning_codes": [],
        "path": path,
        "expected_manuscript_sha256": expected_sha,
        "artifact_status": artifact_status,
    }


def _stale_result(path: Any, expected_sha: str, actual_sha: str, artifact_status: str) -> dict[str, Any]:
    return {
        "status": "fail",
        "failing_codes": ["figure_placement_review_stale"],
        "warning_codes": [],
        "path": path,
        "expected_manuscript_sha256": expected_sha,
        "actual_manuscript_sha256": actual_sha,
        "artifact_status": artifact_status,
    }


def _bound_result(path: Any, payload: dict[str, Any], artifact_status: str) -> dict[str, Any]:
    failing_codes = _normalized_codes(payload.get("failing_codes"))
    warning_codes = _normalized_codes(payload.get("warning_codes"))
    return {
        "status": _figure_grounding_status(artifact_status, failing_codes, warning_codes),
        "failing_codes": failing_codes,
        "warning_codes": warning_codes,
        "path": path,
        "artifact_status": artifact_status,
        "figures": figure_grounding_issue_figures(payload),
    }


def _normalized_codes(value: Any) -> list[str]:
    return sorted(dict.fromkeys(str(code) for code in value or [] if str(code).strip()))


def _figure_grounding_status(artifact_status: str, failing_codes: list[str], warning_codes: list[str]) -> str:
    if failing_codes or artifact_status in {"fail", "failed", "block", "blocked"}:
        return "fail"
    if warning_codes or artifact_status in {"warn", "warning"}:
        return "warn"
    return "pass"
