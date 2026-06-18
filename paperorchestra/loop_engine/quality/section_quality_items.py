from __future__ import annotations

from typing import Any


def _section_quality_groups(sections: list[dict[str, Any]], thresholds: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    low_sections: list[dict[str, Any]] = []
    required_fix_sections: list[dict[str, Any]] = []
    process_residue_sections: list[dict[str, Any]] = []
    for item in sections:
        score = _numeric_score(item.get("score"))
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
    return low_sections, required_fix_sections, process_residue_sections


def _numeric_score(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _section_failing_codes(
    *,
    sections: list[dict[str, Any]],
    overall_score: float | None,
    thresholds: dict[str, Any],
    low_sections: list[dict[str, Any]],
    required_fix_sections: list[dict[str, Any]],
    process_residue_sections: list[dict[str, Any]],
) -> list[str]:
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
    return sorted(set(failing_codes))
