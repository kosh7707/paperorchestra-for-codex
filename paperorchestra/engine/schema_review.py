from __future__ import annotations

from paperorchestra.engine.schema_common import _closed_object_schema, _string_list_schema

_REVIEW_AXIS_SCORE_SCHEMA = _closed_object_schema(
    {
        "score": {"type": ["number", "integer"]},
        "justification": {"type": "string"},
    }
)

_REVIEW_AXIS_SCORES_SCHEMA = _closed_object_schema(
    {
        "coverage_and_completeness": _REVIEW_AXIS_SCORE_SCHEMA,
        "relevance_and_focus": _REVIEW_AXIS_SCORE_SCHEMA,
        "critical_analysis_and_synthesis": _REVIEW_AXIS_SCORE_SCHEMA,
        "positioning_and_novelty": _REVIEW_AXIS_SCORE_SCHEMA,
        "organization_and_writing": _REVIEW_AXIS_SCORE_SCHEMA,
        "citation_practices_and_rigor": _REVIEW_AXIS_SCORE_SCHEMA,
    }
)

_REVIEW_CITATION_STATISTICS_SCHEMA = _closed_object_schema(
    {
        "estimated_unique_citations": {"type": ["number", "integer", "string", "null"]},
        "citation_density_assessment": {"type": ["string", "null"]},
        "breadth_across_subareas": {"type": ["string", "null"]},
        "comparison_to_baseline": {"type": ["string", "null"]},
        "notes": {"type": ["string", "null"]},
    }
)

_REVIEW_PENALTY_SCHEMA = _closed_object_schema(
    {
        "reason": {"type": "string"},
        "points_deducted": {"type": ["number", "integer"]},
    }
)

_REVIEW_SUMMARY_SCHEMA = _closed_object_schema(
    {
        "strengths": _string_list_schema(),
        "weaknesses": _string_list_schema(),
        "top_improvements": _string_list_schema(),
    }
)

REVIEW_SCHEMA = {
    **_closed_object_schema(
        {
            "paper_title": {"type": ["string", "null"]},
            "citation_statistics": _REVIEW_CITATION_STATISTICS_SCHEMA,
            "overall_score": {"type": ["number", "integer"]},
            "axis_scores": _REVIEW_AXIS_SCORES_SCHEMA,
            "penalties": {"type": "array", "items": _REVIEW_PENALTY_SCHEMA},
            "summary": _REVIEW_SUMMARY_SCHEMA,
            "questions": _string_list_schema(),
        },
        required=["paper_title", "citation_statistics", "axis_scores", "penalties", "summary", "questions", "overall_score"],
    )
}
