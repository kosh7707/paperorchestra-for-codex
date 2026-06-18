from __future__ import annotations

from pathlib import Path
from typing import Any

from .policy import SECTION_REVIEW_THRESHOLDS
from .utils import _file_sha256, _read_json_if_exists
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
        "load_bearing_context": (
            "raw section scores are advisory diagnostics; quality-eval may only consume section failing_codes inside Tier 3 "
            "after upstream Tier 0-2 pass"
        ),
        "expected_manuscript_sha256": current_sha,
        "actual_manuscript_sha256": payload.get("manuscript_sha256"),
    }
