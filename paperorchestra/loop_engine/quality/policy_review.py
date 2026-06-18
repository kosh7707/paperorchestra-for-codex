from __future__ import annotations

REQUIRED_REVIEW_AXES = {
    "coverage_and_completeness",
    "relevance_and_focus",
    "critical_analysis_and_synthesis",
    "positioning_and_novelty",
    "organization_and_writing",
    "citation_practices_and_rigor",
}

MODE_THRESHOLDS = {
    "draft": {"overall_min": 0.0, "axis_min": 0.0},
    "ralph": {"overall_min": 70.0, "axis_min": 60.0},
    "claim_safe": {"overall_min": 80.0, "axis_min": 70.0},
}

SECTION_REVIEW_THRESHOLDS = {
    "draft": {"overall_min": 45.0, "section_min": 35.0, "required_fixes_fail": False},
    "ralph": {"overall_min": 70.0, "section_min": 60.0, "required_fixes_fail": True},
    "claim_safe": {"overall_min": 75.0, "section_min": 70.0, "required_fixes_fail": True},
}

__all__ = ["MODE_THRESHOLDS", "REQUIRED_REVIEW_AXES", "SECTION_REVIEW_THRESHOLDS"]
