from __future__ import annotations

from typing import Any

from paperorchestra.core.errors import ContractError


VALID_ASPECT_RATIOS = {"1:1", "1:4", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
VALID_PLOT_TYPES = {"plot", "diagram"}


def _closed_object_schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required or list(properties.keys()),
        "properties": properties,
    }


def _string_list_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


_OUTLINE_PLOTTING_ITEM_SCHEMA = _closed_object_schema(
    {
        "figure_id": {"type": "string"},
        "title": {"type": "string"},
        "plot_type": {"type": "string"},
        "data_source": {"type": "string"},
        "objective": {"type": "string"},
        "aspect_ratio": {"type": "string"},
    }
)

_OUTLINE_INTRODUCTION_STRATEGY_SCHEMA = _closed_object_schema(
    {
        "hook_hypothesis": {"type": "string"},
        "problem_gap_hypothesis": {"type": "string"},
        "search_directions": _string_list_schema(),
    }
)

_OUTLINE_RELATED_SUBSECTION_SCHEMA = _closed_object_schema(
    {
        "subsection_title": {"type": "string"},
        "methodology_cluster": {"type": "string"},
        "sota_investigation_mission": {"type": "string"},
        "limitation_hypothesis": {"type": "string"},
        "limitation_search_queries": _string_list_schema(),
        "bridge_to_our_method": {"type": "string"},
    }
)

_OUTLINE_RELATED_WORK_STRATEGY_SCHEMA = _closed_object_schema(
    {
        "overview": {"type": "string"},
        "subsections": {"type": "array", "items": _OUTLINE_RELATED_SUBSECTION_SCHEMA},
    }
)

_OUTLINE_INTRO_RELATED_WORK_PLAN_SCHEMA = _closed_object_schema(
    {
        "introduction_strategy": _OUTLINE_INTRODUCTION_STRATEGY_SCHEMA,
        "related_work_strategy": _OUTLINE_RELATED_WORK_STRATEGY_SCHEMA,
    }
)

_OUTLINE_SECTION_SUBSECTION_SCHEMA = _closed_object_schema(
    {
        "subsection_title": {"type": "string"},
        "content_bullets": _string_list_schema(),
        "citation_hints": _string_list_schema(),
    }
)

_OUTLINE_SECTION_ITEM_SCHEMA = _closed_object_schema(
    {
        "section_title": {"type": "string"},
        "subsections": {"type": "array", "items": _OUTLINE_SECTION_SUBSECTION_SCHEMA},
    }
)

_PLOT_MANIFEST_ITEM_SCHEMA = _closed_object_schema(
    {
        "figure_id": {"type": "string"},
        "title": {"type": "string"},
        "plot_type": {"type": "string"},
        "data_source": {"type": "string"},
        "objective": {"type": "string"},
        "aspect_ratio": {"type": "string"},
        "rendering_brief": {"type": "string"},
        "caption": {"type": "string"},
        "source_fidelity_notes": {"type": "string"},
    }
)

_CANDIDATE_ITEM_SCHEMA = _closed_object_schema(
    {
        "title_guess": {"type": "string"},
        "why_relevant": {"type": "string"},
        "origin_query": {"type": "string"},
        "role_guess": {"type": "string"},
        "discovery_source": {"type": "string"},
        "discovery_sources": _string_list_schema(),
    }
)

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

OUTLINE_SCHEMA = {
    **_closed_object_schema(
        {
            "plotting_plan": {"type": "array", "items": _OUTLINE_PLOTTING_ITEM_SCHEMA},
            "intro_related_work_plan": _OUTLINE_INTRO_RELATED_WORK_PLAN_SCHEMA,
            "section_plan": {"type": "array", "items": _OUTLINE_SECTION_ITEM_SCHEMA},
        }
    )
}
PLOT_SCHEMA = {
    **_closed_object_schema(
        {
            "figures": {"type": "array", "items": _PLOT_MANIFEST_ITEM_SCHEMA},
        }
    )
}
CANDIDATE_SCHEMA = {
    **_closed_object_schema(
        {
            "macro_candidates": {"type": "array", "items": _CANDIDATE_ITEM_SCHEMA},
            "micro_candidates": {"type": "array", "items": _CANDIDATE_ITEM_SCHEMA},
        }
    )
}

_PRIOR_WORK_ENTRY_SCHEMA = _closed_object_schema(
    {
        "title": {"type": "string"},
        "authors": _string_list_schema(),
        "year": {"type": ["integer", "null"]},
        "venue": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "doi": {"type": ["string", "null"]},
        "source": {"type": "string"},
        "why_relevant": {"type": "string"},
        "provenance_notes": _string_list_schema(),
    }
)
PRIOR_WORK_SEED_SCHEMA = _closed_object_schema(
    {
        "references": {"type": "array", "items": _PRIOR_WORK_ENTRY_SCHEMA},
        "research_notes": _string_list_schema(),
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


def validate_outline(data: dict[str, Any]) -> None:
    missing = {"plotting_plan", "intro_related_work_plan", "section_plan"} - set(data)
    if missing:
        raise ContractError(f"Outline missing required keys: {sorted(missing)}")
    if not isinstance(data["plotting_plan"], list):
        raise ContractError("plotting_plan must be a list.")
    for plot in data["plotting_plan"]:
        for key in ["figure_id", "title", "plot_type", "data_source", "objective", "aspect_ratio"]:
            if key not in plot:
                raise ContractError(f"plotting_plan item missing key: {key}")
        if plot["plot_type"] not in VALID_PLOT_TYPES:
            raise ContractError(f"Invalid plot_type: {plot['plot_type']}")
        if plot["aspect_ratio"] not in VALID_ASPECT_RATIOS:
            raise ContractError(f"Invalid aspect_ratio: {plot['aspect_ratio']}")


def _normalize_plot_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in VALID_PLOT_TYPES:
        return normalized
    if "diagram" in normalized:
        return "diagram"
    return "plot"


def _normalize_aspect_ratio(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in VALID_ASPECT_RATIOS:
        return normalized
    aliases = {
        "wide": "16:9",
        "landscape": "16:9",
        "standard": "4:3",
        "square": "1:1",
        "portrait": "3:4",
    }
    return aliases.get(normalized, "16:9")


def normalize_outline_payload(payload: dict[str, Any]) -> dict[str, Any]:
    plotting_plan = payload.get("plotting_plan")
    if isinstance(plotting_plan, list):
        for item in plotting_plan:
            if not isinstance(item, dict):
                continue
            plot_type = item.get("plot_type")
            if isinstance(plot_type, str) and plot_type not in VALID_PLOT_TYPES:
                original = plot_type
                item["plot_type"] = _normalize_plot_type(plot_type)
                objective = item.get("objective", "")
                if isinstance(objective, str) and original.lower() not in objective.lower():
                    item["objective"] = f"{objective} Original requested chart form: {original}."
            aspect_ratio = item.get("aspect_ratio")
            if isinstance(aspect_ratio, str) and aspect_ratio not in VALID_ASPECT_RATIOS:
                item["aspect_ratio"] = _normalize_aspect_ratio(aspect_ratio)
    return payload


def validate_plot_manifest(data: dict[str, Any]) -> None:
    if "figures" not in data or not isinstance(data["figures"], list):
        raise ContractError("Plot manifest must contain a figures list.")
    for figure in data["figures"]:
        for key in [
            "figure_id",
            "title",
            "plot_type",
            "data_source",
            "objective",
            "aspect_ratio",
            "rendering_brief",
            "caption",
            "source_fidelity_notes",
        ]:
            if key not in figure:
                raise ContractError(f"Plot manifest figure missing key: {key}")
