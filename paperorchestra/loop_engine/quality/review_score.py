from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.policy import REQUIRED_REVIEW_AXES
from paperorchestra.loop_engine.quality.utils import _file_sha256


def _numeric_axis_scores(review: dict[str, Any]) -> dict[str, float]:
    axes: dict[str, float] = {}
    axis_scores = review.get("axis_scores") if isinstance(review, dict) else {}
    if isinstance(axis_scores, dict):
        for axis, value in axis_scores.items():
            if isinstance(value, dict):
                score = value.get("score")
            else:
                score = value
            if isinstance(score, (int, float)):
                axes[str(axis)] = float(score)
    return axes


def _nonempty_string(value: Any, *, min_len: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_len


def _review_shape_failures(review: dict[str, Any], *, quality_mode: str) -> list[str]:
    if quality_mode != "claim_safe":
        return []
    failures: list[str] = []
    if review.get("schema_version") != "paper-review/1":
        failures.append("review_schema_invalid")
    axis_scores = review.get("axis_scores")
    if not isinstance(axis_scores, dict) or set(axis_scores) != REQUIRED_REVIEW_AXES:
        failures.append("review_axes_incomplete")
    else:
        for axis in sorted(REQUIRED_REVIEW_AXES):
            payload = axis_scores.get(axis)
            score = payload.get("score") if isinstance(payload, dict) else payload
            justification = payload.get("justification") if isinstance(payload, dict) else None
            if not isinstance(score, (int, float)) or not (0 <= float(score) <= 100):
                failures.append("review_axis_invalid")
            if not _nonempty_string(justification, min_len=10):
                failures.append("review_axis_justification_missing")
    summary = review.get("summary")
    if not isinstance(summary, dict) or not isinstance(summary.get("weaknesses"), list) or not isinstance(summary.get("top_improvements"), list):
        failures.append("review_summary_missing")
    if not isinstance(review.get("penalties"), list):
        failures.append("review_penalties_missing")
    return sorted(dict.fromkeys(failures))


def _review_provenance_failures(review: dict[str, Any], *, current_sha: str | None, quality_mode: str) -> tuple[list[str], dict[str, Any]]:
    if quality_mode != "claim_safe":
        return [], {"status": "not_required"}
    provenance = review.get("review_provenance")
    if not isinstance(provenance, dict):
        return ["review_provenance_missing"], {"status": "fail", "reason": "missing"}
    failures: list[str] = []
    if provenance.get("schema_version") != "review-provenance/1":
        failures.append("review_provenance_legacy_untrusted")
    if provenance.get("stage") != "review":
        failures.append("review_provenance_stage_mismatch")
    if current_sha and provenance.get("manuscript_sha256") != current_sha:
        failures.append("review_provenance_stale")
    for key, code in [
        ("prompt_trace_meta_path", "review_provenance_missing"),
        ("provider_identity_path", "review_provenance_missing"),
        ("lane_manifest_path", "review_provenance_missing"),
    ]:
        value = provenance.get(key)
        if not value or not Path(str(value)).exists():
            failures.append(code)
    for path_key, sha_key in [
        ("prompt_trace_meta_path", "prompt_trace_meta_sha256"),
        ("provider_identity_path", "provider_identity_sha256"),
        ("lane_manifest_path", "lane_manifest_sha256"),
    ]:
        path = provenance.get(path_key)
        expected = provenance.get(sha_key)
        actual = _file_sha256(path) if isinstance(path, str) else None
        if expected and actual and expected != actual:
            failures.append("review_provenance_stale")
    return sorted(dict.fromkeys(failures)), {
        "status": "fail" if failures else "pass",
        "reviewer_label": provenance.get("reviewer_label"),
        "provider_name": provenance.get("provider_name"),
        "provider_command_digest": provenance.get("provider_command_digest"),
        "prompt_trace_meta_path": provenance.get("prompt_trace_meta_path"),
        "provider_identity_path": provenance.get("provider_identity_path"),
        "lane_manifest_path": provenance.get("lane_manifest_path"),
        "failing_codes": sorted(dict.fromkeys(failures)),
    }


def _anti_inflation_violations(overall_score: float | None, axis_scores: dict[str, float]) -> list[str]:
    violations: list[str] = []
    if overall_score is None:
        return violations
    if any(score < 50 for score in axis_scores.values()) and overall_score > 75:
        violations.append("overall_score_above_75_with_sub50_axis")
    if overall_score > 90:
        violations.append("overall_score_above_90_requires_exceptional_evidence")
    critical_score = axis_scores.get("critical_analysis_and_synthesis")
    if critical_score is not None and critical_score > 60 and overall_score <= 55:
        violations.append("critical_analysis_above_60_with_low_overall_score")
    return violations
