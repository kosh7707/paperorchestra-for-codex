from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.policy import SECTION_REVIEW_THRESHOLDS
from paperorchestra.loop_engine.quality.section_quality_items import _numeric_score, _section_failing_codes, _section_quality_groups
from paperorchestra.loop_engine.quality.section_quality_path import _section_review_path
from paperorchestra.loop_engine.quality.section_quality_trust import (
    _current_manuscript_sha,
    _loaded_section_review,
    _section_review_trust_failure,
)


def _section_quality_check(cwd: str | Path | None, state, *, quality_mode: str) -> dict[str, Any]:
    path = _section_review_path(cwd, state)
    payload = _loaded_section_review(path)
    current_sha = _current_manuscript_sha(state)
    trust_failure = _section_review_trust_failure(path=path, payload=payload, current_sha=current_sha)
    if trust_failure is not None:
        return trust_failure
    assert payload is not None
    thresholds = SECTION_REVIEW_THRESHOLDS[quality_mode]
    overall_score = _numeric_score(payload.get("overall_section_score"))
    sections = [item for item in payload.get("sections") or [] if isinstance(item, dict)]
    low_sections, required_fix_sections, process_residue_sections = _section_quality_groups(sections, thresholds)
    failing_codes = _section_failing_codes(
        sections=sections,
        overall_score=overall_score,
        thresholds=thresholds,
        low_sections=low_sections,
        required_fix_sections=required_fix_sections,
        process_residue_sections=process_residue_sections,
    )
    return {
        "status": "fail" if failing_codes else "pass",
        "path": str(path),
        "failing_codes": failing_codes,
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
