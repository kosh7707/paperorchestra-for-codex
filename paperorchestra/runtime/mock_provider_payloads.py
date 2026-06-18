from __future__ import annotations

import json
import re

from paperorchestra.domains import get_domain
from paperorchestra.runtime.provider_base import CompletionRequest

FIGURE_RENDERING_BRIEF = (
    "A conceptual pipeline diagram connecting inputs, outline, plot generation, "
    "literature review, writing, and refinement."
)
FIGURE_CAPTION = (
    "Overview of the multi-agent writing pipeline and its artifact flow from raw inputs "
    "to a refined manuscript."
)
FIGURE_FIDELITY_NOTES = "mixed: concept-grounded structure with references to experimental-log-driven outputs."
INTRO_HOOK = "High-quality literature review and grounded writing remain bottlenecks in AI paper drafting."
INTRO_GAP = "Existing autonomous writers under-cite and fail to ground manuscript structure in raw materials."
RELATED_OVERVIEW = (
    "Compare end-to-end research agents, literature-review systems, "
    "and structure-grounded writing systems."
)
RELATED_BRIDGE = "The proposed pipeline decouples writing from experimentation and grounds citations via verification."


def build_prior_work_seed_response() -> str:
    return json.dumps(
        {
            "references": [dict(item) for item in get_domain().mock_prior_work_references],
            "research_notes": ["Mock provider returns canonical seed examples without live web access."],
        },
        indent=2,
    )


def build_citation_support_response(request: CompletionRequest) -> str:
    ids = re.findall(r'"id"\s*:\s*"(cite-\d+)"', request.user_prompt)
    return json.dumps(
        {
            "items": [
                {
                    "id": item_id,
                    "support_status": "needs_manual_check",
                    "risk": "medium",
                    "claim_type": "background",
                    "evidence": [],
                    "reasoning": "Mock provider cannot perform live web/source inspection.",
                    "suggested_fix": "Run a web-search-capable provider or manually verify this cited sentence.",
                }
                for item_id in ids
            ],
            "research_notes": ["Mock provider does not claim cited-sentence support."],
        },
        indent=2,
    )


def _mock_candidate_payload() -> dict:
    return {
        "macro_candidates": [
            {
                "title_guess": "AutoSurvey2",
                "why_relevant": "Survey-generation baseline for literature synthesis.",
                "origin_query": "automated literature review generation",
                "role_guess": "macro",
                "discovery_source": "model",
                "discovery_sources": ["model"],
            }
        ],
        "micro_candidates": [
            {
                "title_guess": "LiRA",
                "why_relevant": "Multi-agent literature review system.",
                "origin_query": "multi-agent literature review generation",
                "role_guess": "micro",
                "discovery_source": "model",
                "discovery_sources": ["model"],
            }
        ],
    }


def _framework_figure_base() -> dict:
    return {
        "figure_id": "fig_framework_overview",
        "title": "Framework overview",
        "plot_type": "diagram",
        "data_source": "both",
        "aspect_ratio": "16:9",
    }


def _mock_figure_payload() -> dict:
    figure = _framework_figure_base()
    figure.update(
        {
            "objective": "Show the end-to-end writing pipeline and artifact flow.",
            "rendering_brief": FIGURE_RENDERING_BRIEF,
            "caption": FIGURE_CAPTION,
            "source_fidelity_notes": FIGURE_FIDELITY_NOTES,
        }
    )
    return {"figures": [figure]}


def _mock_outline_payload() -> dict:
    return {
        "plotting_plan": [
            {
                **_framework_figure_base(),
                "objective": "Diagram showing the full writing pipeline and data flow.",
            }
        ],
        "intro_related_work_plan": {
            "introduction_strategy": {
                "hook_hypothesis": INTRO_HOOK,
                "problem_gap_hypothesis": INTRO_GAP,
                "search_directions": [
                    "automated research paper writing literature review benchmark",
                    "multi-agent literature review generation",
                    "submission-ready latex manuscript generation",
                ],
            },
            "related_work_strategy": {
                "overview": RELATED_OVERVIEW,
                "subsections": [
                    {
                        "subsection_title": "Related Work: Autonomous research agents",
                        "methodology_cluster": "End-to-end research agents",
                        "sota_investigation_mission": "Find recent autonomous research systems before the cutoff.",
                        "limitation_hypothesis": "These systems are tightly coupled to internal experimentation loops.",
                        "limitation_search_queries": [
                            "autonomous research agent manuscript generation",
                            "paper writing coupled to experiment pipeline",
                        ],
                        "bridge_to_our_method": RELATED_BRIDGE,
                    }
                ],
            },
        },
        "section_plan": [
            {
                "section_title": "Method",
                "subsections": [
                    {
                        "subsection_title": "Pipeline Overview",
                        "content_bullets": [
                            "Describe the five-step orchestration pipeline.",
                            "Explain the inputs and generated artifact flow.",
                        ],
                        "citation_hints": [
                            "research paper or technical report introducing 'Semantic Scholar API'"
                        ],
                    }
                ],
            }
        ],
    }


def _mock_review_payload(request: CompletionRequest) -> dict:
    paper_text = request.user_prompt.lower()
    score = 72
    if "refined mock paper" in paper_text:
        score = 78
    if "regressed mock paper" in paper_text:
        score = 61
    return {
        "paper_title": "Mock Paper",
        "citation_statistics": {
            "estimated_unique_citations": 12,
            "citation_density_assessment": "appropriate",
            "breadth_across_subareas": "moderate",
            "comparison_to_baseline": "roughly on par with the provided baseline expectation",
            "notes": "Mock citation statistics for regression tests.",
        },
        "axis_scores": {
            "coverage_and_completeness": {"score": score, "justification": "Coverage appears reasonably grounded."},
            "relevance_and_focus": {"score": max(score - 2, 0), "justification": "Focus remains reasonably grounded."},
            "critical_analysis_and_synthesis": {
                "score": max(score - 4, 0),
                "justification": "Synthesis is acceptable in the mock path.",
            },
            "positioning_and_novelty": {
                "score": max(score - 5, 0),
                "justification": "Positioning is acceptable in the mock path.",
            },
            "organization_and_writing": {
                "score": score,
                "justification": "Organization is acceptable in the mock path.",
            },
            "citation_practices_and_rigor": {
                "score": max(score - 3, 0),
                "justification": "Citation rigor is acceptable in the mock path.",
            },
        },
        "penalties": [],
        "summary": {
            "strengths": ["Grounded artifact use"],
            "weaknesses": ["Needs stronger synthesis"],
            "top_improvements": ["Clarify literature positioning"],
        },
        "overall_score": score,
        "questions": ["Clarify why the pipeline is decoupled from experiment generation."],
    }


def _is_candidate_request(system_prompt: str) -> bool:
    return "macro_candidates" in system_prompt


def _is_figure_request(system_prompt: str) -> bool:
    return "top-level key named figures" in system_prompt


def _is_outline_request(system_prompt: str) -> bool:
    return "plotting_plan" in system_prompt or "outline" in system_prompt


def _is_review_request(system_prompt: str) -> bool:
    return (
        ("reviewer" in system_prompt or "overall_score" in system_prompt)
        and "reviewer_feedback" not in system_prompt
    )


JSON_RESPONSE_BUILDERS = (
    (_is_candidate_request, lambda request: _mock_candidate_payload()),
    (_is_figure_request, lambda request: _mock_figure_payload()),
    (_is_outline_request, lambda request: _mock_outline_payload()),
    (_is_review_request, _mock_review_payload),
)


def build_json_response(request: CompletionRequest, system_prompt: str) -> str:
    for predicate, builder in JSON_RESPONSE_BUILDERS:
        if predicate(system_prompt):
            return json.dumps(builder(request), indent=2)
    return json.dumps({"ok": True}, indent=2)
