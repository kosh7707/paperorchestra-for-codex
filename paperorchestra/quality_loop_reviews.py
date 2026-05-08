from __future__ import annotations

from pathlib import Path
from typing import Any

from .quality_loop_policy import MODE_THRESHOLDS, REQUIRED_REVIEW_AXES, SECTION_REVIEW_THRESHOLDS, TIER2_CLAIM_CODES
from .quality_loop_utils import _file_sha256, _read_json_if_exists
from .session import artifact_path, runtime_root


def _validation_issue_counts(reproducibility: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reproducibility.get("validation_warning_reports") or []:
        payload = _read_json_if_exists(report.get("path"))
        if not isinstance(payload, dict):
            continue
        for issue in payload.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "")
            if code:
                counts[code] = counts.get(code, 0) + 1
    for issue in reproducibility.get("strict_content_gate_issues") or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "")
        if code in TIER2_CLAIM_CODES:
            counts[code] = max(counts.get(code, 0), 1)
    return counts

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

def _latest_review_payload(state) -> tuple[str | None, dict[str, Any] | None]:
    if state.artifacts.latest_review_json:
        payload = _read_json_if_exists(state.artifacts.latest_review_json)
        if isinstance(payload, dict):
            return state.artifacts.latest_review_json, payload
    if state.review_history:
        raw_path = state.review_history[-1].raw_path
        payload = _read_json_if_exists(raw_path)
        if isinstance(payload, dict):
            return raw_path, payload
    return None, None

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

def _review_score_check(state, *, quality_mode: str) -> dict[str, Any]:
    path, review = _latest_review_payload(state)
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if not isinstance(review, dict):
        return {
            "status": "fail",
            "path": path,
            "failing_codes": ["review_score_missing"],
            "overall_score": None,
            "axis_scores": {},
            "anti_inflation_triggered": False,
            "anti_inflation_violations": [],
        }
    shape_failures = _review_shape_failures(review, quality_mode=quality_mode)
    provenance_failures, provenance_check = _review_provenance_failures(review, current_sha=current_sha, quality_mode=quality_mode)
    if not review.get("manuscript_sha256"):
        return {
            "status": "fail",
            "path": path,
            "failing_codes": sorted(dict.fromkeys(["review_score_legacy_untrusted"] + shape_failures + provenance_failures)),
            "overall_score": review.get("overall_score"),
            "axis_scores": _numeric_axis_scores(review),
            "anti_inflation_triggered": False,
            "anti_inflation_violations": [],
            "provenance": provenance_check,
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": review.get("manuscript_sha256"),
        }
    if current_sha and review.get("manuscript_sha256") != current_sha:
        return {
            "status": "fail",
            "path": path,
            "failing_codes": sorted(dict.fromkeys(["review_score_stale"] + shape_failures + provenance_failures)),
            "overall_score": review.get("overall_score"),
            "axis_scores": _numeric_axis_scores(review),
            "anti_inflation_triggered": False,
            "anti_inflation_violations": [],
            "provenance": provenance_check,
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": review.get("manuscript_sha256"),
        }
    thresholds = MODE_THRESHOLDS[quality_mode]
    raw_overall = review.get("overall_score")
    overall_score = float(raw_overall) if isinstance(raw_overall, (int, float)) else None
    axis_scores = _numeric_axis_scores(review)
    anti = _anti_inflation_violations(overall_score, axis_scores)
    failing_codes: list[str] = []
    failing_codes.extend(shape_failures)
    failing_codes.extend(provenance_failures)
    if overall_score is None:
        failing_codes.append("review_score_missing")
    elif overall_score < thresholds["overall_min"]:
        failing_codes.append("review_overall_below_threshold")
    if axis_scores and min(axis_scores.values()) < thresholds["axis_min"]:
        failing_codes.append("review_axis_below_threshold")
    if anti:
        failing_codes.append("review_anti_inflation")
    return {
        "status": "fail" if failing_codes else "pass",
        "path": path,
        "failing_codes": failing_codes,
        "overall_score": overall_score,
        "axis_scores": axis_scores,
        "anti_inflation_triggered": bool(anti),
        "anti_inflation_violations": anti,
        "provenance": provenance_check,
        "expected_manuscript_sha256": current_sha,
        "actual_manuscript_sha256": review.get("manuscript_sha256"),
    }

def _reviewer_identity(review: dict[str, Any]) -> str | None:
    provenance = review.get("review_provenance") if isinstance(review, dict) else None
    if not isinstance(provenance, dict):
        return None
    for key in ("reviewer_label", "provider_command_digest", "prompt_trace_meta_sha256", "provider_name"):
        value = provenance.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None

def _current_review_records(state, current_sha: str | None) -> list[dict[str, Any]]:
    paths: list[str] = []
    if state.artifacts.latest_review_json:
        paths.append(state.artifacts.latest_review_json)
    for snapshot in state.review_history:
        if snapshot.raw_path:
            paths.append(snapshot.raw_path)
    records: list[dict[str, Any]] = []
    for raw_path in sorted(dict.fromkeys(paths)):
        payload = _read_json_if_exists(raw_path)
        if not isinstance(payload, dict):
            continue
        if current_sha and payload.get("manuscript_sha256") != current_sha:
            continue
        if _review_shape_failures(payload, quality_mode="claim_safe"):
            continue
        provenance_failures, _ = _review_provenance_failures(payload, current_sha=current_sha, quality_mode="claim_safe")
        if provenance_failures:
            continue
        identity = _reviewer_identity(payload)
        if not identity:
            continue
        records.append({"path": raw_path, "sha256": _file_sha256(raw_path), "identity": identity})
    return records

def _reviewer_acceptance_path(cwd: str | Path | None) -> Path:
    return runtime_root(cwd) / "reviewer-independence-acceptance.json"

def _reviewer_independence_acceptance(cwd: str | Path | None, current_sha: str | None, records: list[dict[str, Any]]) -> dict[str, Any]:
    path = _reviewer_acceptance_path(cwd)
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {"status": "missing", "path": str(path), "failing_codes": ["reviewer_independence_missing"]}
    failures: list[str] = []
    if payload.get("schema_version") != "reviewer-independence-acceptance/1":
        failures.append("reviewer_independence_acceptance_legacy_untrusted")
    if payload.get("source") == "codex_operator" or payload.get("not_independent_human_review") is True:
        failures.append("reviewer_independence_acceptance_operator_not_independent")
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        failures.append("reviewer_independence_acceptance_stale")
    accepted_hashes = {
        str(item.get("sha256"))
        for item in payload.get("review_artifacts") or []
        if isinstance(item, dict) and item.get("sha256")
    }
    current_hashes = {str(record.get("sha256")) for record in records if record.get("sha256")}
    if not current_hashes or not current_hashes.issubset(accepted_hashes):
        failures.append("reviewer_independence_acceptance_stale")
    if not _nonempty_string(payload.get("rationale"), min_len=10) or not _nonempty_string(payload.get("operator_label"), min_len=2):
        failures.append("reviewer_independence_acceptance_incomplete")
    if not _nonempty_string(payload.get("accepted_at"), min_len=10):
        failures.append("reviewer_independence_acceptance_incomplete")
    writer_refiner = payload.get("writer_refiner_provenance")
    if not isinstance(writer_refiner, list) or not writer_refiner:
        failures.append("reviewer_independence_acceptance_incomplete")
    else:
        for item in writer_refiner:
            if not isinstance(item, dict):
                failures.append("reviewer_independence_acceptance_incomplete")
                continue
            path_value = item.get("path")
            expected_sha = item.get("sha256")
            actual_sha = _file_sha256(path_value) if isinstance(path_value, str) else None
            if not path_value or not expected_sha or not actual_sha or expected_sha != actual_sha:
                failures.append("reviewer_independence_acceptance_stale")
    return {
        "status": "fail" if failures else "pass",
        "path": str(path),
        "failing_codes": sorted(dict.fromkeys(failures)),
        "review_artifact_count": len(payload.get("review_artifacts") or []),
    }

def _reviewer_independence_check(cwd: str | Path | None, state, *, quality_mode: str) -> dict[str, Any]:
    if quality_mode != "claim_safe":
        return {"status": "not_required", "failing_codes": []}
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    records = _current_review_records(state, current_sha)
    identities = sorted({str(record.get("identity")) for record in records if record.get("identity")})
    acceptance = _reviewer_independence_acceptance(cwd, current_sha, records)
    if len(identities) >= 2:
        return {
            "status": "pass",
            "failing_codes": [],
            "current_review_count": len(records),
            "distinct_reviewer_count": len(identities),
            "reviewers": identities,
            "acceptance": acceptance,
        }
    if acceptance.get("status") == "pass":
        return {
            "status": "pass",
            "failing_codes": [],
            "current_review_count": len(records),
            "distinct_reviewer_count": len(identities),
            "reviewers": identities,
            "acceptance": acceptance,
            "operator_override_used": True,
        }
    codes = ["reviewer_independence_missing"]
    codes.extend(acceptance.get("failing_codes") or [])
    return {
        "status": "fail",
        "failing_codes": sorted(dict.fromkeys(codes)),
        "current_review_count": len(records),
        "distinct_reviewer_count": len(identities),
        "reviewers": identities,
        "acceptance": acceptance,
    }

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

def _section_quality_check(cwd: str | Path | None, state, *, quality_mode: str) -> dict[str, Any]:
    path = _section_review_path(cwd, state)
    payload = _read_json_if_exists(path)
    current_sha = _file_sha256(state.artifacts.paper_full_tex)
    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "path": str(path),
            "failing_codes": ["section_review_missing"],
            "overall_section_score": None,
            "low_sections": [],
            "sections_with_required_fixes": [],
        }
    if payload.get("schema_version") != "section-review/1" or not payload.get("manuscript_sha256"):
        return {
            "status": "fail",
            "path": str(path),
            "failing_codes": ["section_review_legacy_untrusted"],
            "overall_section_score": payload.get("overall_section_score"),
            "low_sections": [],
            "sections_with_required_fixes": [],
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": payload.get("manuscript_sha256"),
        }
    if current_sha and payload.get("manuscript_sha256") != current_sha:
        return {
            "status": "fail",
            "path": str(path),
            "failing_codes": ["section_review_stale"],
            "overall_section_score": payload.get("overall_section_score"),
            "low_sections": [],
            "sections_with_required_fixes": [],
            "expected_manuscript_sha256": current_sha,
            "actual_manuscript_sha256": payload.get("manuscript_sha256"),
        }
    thresholds = SECTION_REVIEW_THRESHOLDS[quality_mode]
    overall = payload.get("overall_section_score")
    overall_score = float(overall) if isinstance(overall, (int, float)) else None
    sections = [item for item in payload.get("sections") or [] if isinstance(item, dict)]
    low_sections: list[dict[str, Any]] = []
    required_fix_sections: list[dict[str, Any]] = []
    process_residue_sections: list[dict[str, Any]] = []
    for item in sections:
        raw_score = item.get("score")
        score = float(raw_score) if isinstance(raw_score, (int, float)) else None
        title = str(item.get("section_title") or "unknown")
        verdict = str(item.get("verdict") or "")
        fixes = [str(fix) for fix in item.get("required_fixes") or []]
        process_markers = [str(marker) for marker in item.get("process_residue_markers") or []]
        if score is None or score < thresholds["section_min"] or verdict == "major_revision":
            low_sections.append({"section_title": title, "score": score, "verdict": verdict, "required_fixes": fixes})
        elif thresholds["required_fixes_fail"] and fixes:
            required_fix_sections.append({"section_title": title, "score": score, "verdict": verdict, "required_fixes": fixes})
        if process_markers:
            process_residue_sections.append({"section_title": title, "markers": process_markers})
    failing_codes: list[str] = []
    if not sections:
        failing_codes.append("section_review_empty")
    if overall_score is None or overall_score < thresholds["overall_min"]:
        failing_codes.append("section_quality_below_threshold")
    if low_sections:
        failing_codes.append("section_quality_below_threshold")
    if required_fix_sections:
        failing_codes.append("section_required_fixes_pending")
    if process_residue_sections:
        failing_codes.append("section_process_residue_detected")
    return {
        "status": "fail" if failing_codes else "pass",
        "path": str(path),
        "failing_codes": sorted(set(failing_codes)),
        "thresholds": thresholds,
        "overall_section_score": overall_score,
        "low_sections": low_sections,
        "sections_with_required_fixes": required_fix_sections,
        "sections_with_process_residue": process_residue_sections,
        "score_use": payload.get("score_use"),
        "load_bearing": False,
        "load_bearing_context": "raw section scores are advisory diagnostics; quality-eval may only consume section failing_codes inside Tier 3 after upstream Tier 0-2 pass",
        "expected_manuscript_sha256": current_sha,
        "actual_manuscript_sha256": payload.get("manuscript_sha256"),
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
