from __future__ import annotations

import html
import json
import re

from paperorchestra.domains import get_domain
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class MockProvider(BaseProvider):
    name = "mock"

    def _extract_data_block(self, text: str, name: str) -> str | None:
        pattern = re.compile(rf"<DATA_BLOCK name=\"{re.escape(name)}\">\n(.*?)\n</DATA_BLOCK>", re.DOTALL)
        match = pattern.search(text)
        return html.unescape(match.group(1).strip()) if match else None

    def _extract_citation_keys(self, text: str) -> list[str]:
        checklist = self._extract_data_block(text, "citation_checklist")
        if checklist:
            try:
                parsed = json.loads(checklist)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, str)]
            except json.JSONDecodeError:
                pass
        citation_map = self._extract_data_block(text, "citation_map.json")
        if citation_map:
            try:
                parsed = json.loads(citation_map)
                if isinstance(parsed, dict):
                    return [key for key in parsed.keys() if isinstance(key, str)]
            except json.JSONDecodeError:
                pass
        return []

    def _extract_plot_ids(self, text: str) -> list[str]:
        manifest = self._extract_data_block(text, "plot_manifest.json")
        if not manifest:
            return []
        try:
            parsed = json.loads(manifest)
        except json.JSONDecodeError:
            return []
        figures = parsed.get("figures", []) if isinstance(parsed, dict) else []
        result = []
        for figure in figures:
            if isinstance(figure, dict) and isinstance(figure.get("figure_id"), str):
                result.append(figure["figure_id"])
        return result

    def _extract_plot_asset_paths(self, text: str) -> list[str]:
        payload = self._extract_data_block(text, "plot_assets.json")
        if not payload:
            return []
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return []
        assets = parsed.get("assets", []) if isinstance(parsed, dict) else []
        result = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            snippet_path = asset.get("latex_snippet_path")
            latex_path = asset.get("latex_path")
            filename = asset.get("filename")
            if isinstance(snippet_path, str):
                result.append(snippet_path)
            elif isinstance(latex_path, str):
                result.append(latex_path)
            elif isinstance(filename, str):
                result.append(filename)
        return result

    def _extract_metric_tokens(self, text: str) -> list[str]:
        experimental_log = self._extract_data_block(text, "experimental_log.md") or self._extract_data_block(
            text, "project_experimental_log"
        )
        if not experimental_log:
            return []
        return re.findall(r"\b\d+\.\d+%?\b|\b\d+%", experimental_log)

    def _mock_latex_document(self, request: CompletionRequest, *, refined: bool = False) -> str:
        citation_keys = self._extract_citation_keys(request.user_prompt)
        plot_ids = self._extract_plot_ids(request.user_prompt)
        plot_asset_paths = self._extract_plot_asset_paths(request.user_prompt)
        metric_tokens = self._extract_metric_tokens(request.user_prompt)
        cited = ",".join(citation_keys[: max(1, len(citation_keys))]) if citation_keys else ""
        cite_clause = f"\\cite{{{cited}}}" if cited else ""
        plot_id = plot_ids[0] if plot_ids else "fig_framework_overview"
        asset_filename = plot_asset_paths[0] if plot_asset_paths else None
        metric_sentence = ""
        if metric_tokens:
            metric_sentence = " Reported grounded metrics include " + ", ".join(metric_tokens[:3]) + "."
        title_line = "Refined mock paper." if refined else "Mock paper output."
        figure_body = (
            (f"\\input{{{asset_filename}}}\n" if asset_filename.endswith(".tex") else f"\\includegraphics[width=0.85\\linewidth]{{{asset_filename}}}\n")
            if asset_filename
            else ""
        )
        return f"""```latex
\\documentclass{{article}}
\\usepackage{{graphicx}}
\\begin{{document}}
{title_line}
\\section{{Introduction}}
PaperOrchestra frames manuscript generation as an artifact-driven workflow {cite_clause}.
\\section{{Related Work}}
Prior autonomous writing systems often remain tightly coupled to experimental loops {cite_clause}.
\\section{{Method}}
The pipeline follows staged orchestration and references Figure~\\ref{{{plot_id}}}. The method section is intentionally non-empty in the mock provider so validation exercises a complete manuscript shape: it describes how inputs are converted into an outline, how plot and literature lanes produce artifacts, and how later writing stages consume those artifacts.
\\begin{{figure}}
{figure_body}
\\caption{{Overview of the staged pipeline.}}
\\label{{{plot_id}}}
\\end{{figure}}
\\section{{Experiments}}
The evaluation emphasizes grounded writing and verified citations.{metric_sentence}
\\section{{Conclusion}}
The manuscript remains artifact-first and refinement-gated {cite_clause}.
\\end{{document}}
```"""

    def complete(self, request: CompletionRequest) -> str:
        system = request.system_prompt.lower()
        if (
            "content refinement agent" in system
            or "two fenced code blocks" in system
            or "rebuttal via revision" in system
            or "two distinct code blocks" in system
            or "worklog for the current turn" in system
        ):
            return """```json
{
  "addressed_weaknesses": ["Clarified framing"],
  "integrated_answers": ["Added one explanatory sentence"],
  "actions_taken": ["Rewrote introduction paragraph"]
}
```
""" + self._mock_latex_document(request, refined=True)
        if "prior-work seed generator" in system:
            return json.dumps(
                {
                    "references": [dict(item) for item in get_domain().mock_prior_work_references],
                    "research_notes": ["Mock provider returns canonical seed examples without live web access."],
                },
                indent=2,
            )
        if "citation-support verifier" in system:
            ids = re.findall(r'"id"\s*:\s*"(cite-\d+)"', request.user_prompt)
            items = []
            for item_id in ids:
                items.append(
                    {
                        "id": item_id,
                        "support_status": "needs_manual_check",
                        "risk": "medium",
                        "claim_type": "background",
                        "evidence": [],
                        "reasoning": "Mock provider cannot perform live web/source inspection.",
                        "suggested_fix": "Run a web-search-capable provider or manually verify this cited sentence.",
                    }
                )
            return json.dumps(
                {
                    "items": items,
                    "research_notes": ["Mock provider does not claim cited-sentence support."],
                },
                indent=2,
            )
        if "single, valid json object" in system or "json object" in system:
            if "macro_candidates" in system:
                payload = {
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
                return json.dumps(payload, indent=2)
            if "top-level key named figures" in system:
                payload = {
                    "figures": [
                        {
                            "figure_id": "fig_framework_overview",
                            "title": "Framework overview",
                            "plot_type": "diagram",
                            "data_source": "both",
                            "objective": "Show the end-to-end writing pipeline and artifact flow.",
                            "aspect_ratio": "16:9",
                            "rendering_brief": "A conceptual pipeline diagram connecting inputs, outline, plot generation, literature review, writing, and refinement.",
                            "caption": "Overview of the multi-agent writing pipeline and its artifact flow from raw inputs to a refined manuscript.",
                            "source_fidelity_notes": "mixed: concept-grounded structure with references to experimental-log-driven outputs.",
                        }
                    ]
                }
                return json.dumps(payload, indent=2)
            if "plotting_plan" in system or "outline" in system:
                payload = {
                    "plotting_plan": [
                        {
                            "figure_id": "fig_framework_overview",
                            "title": "Framework overview",
                            "plot_type": "diagram",
                            "data_source": "both",
                            "objective": "Diagram showing the full writing pipeline and data flow.",
                            "aspect_ratio": "16:9",
                        }
                    ],
                    "intro_related_work_plan": {
                        "introduction_strategy": {
                            "hook_hypothesis": "High-quality literature review and grounded writing remain bottlenecks in AI paper drafting.",
                            "problem_gap_hypothesis": "Existing autonomous writers under-cite and fail to ground manuscript structure in raw materials.",
                            "search_directions": [
                                "automated research paper writing literature review benchmark",
                                "multi-agent literature review generation",
                                "submission-ready latex manuscript generation"
                            ],
                        },
                        "related_work_strategy": {
                            "overview": "Compare end-to-end research agents, literature-review systems, and structure-grounded writing systems.",
                            "subsections": [
                                {
                                    "subsection_title": "Related Work: Autonomous research agents",
                                    "methodology_cluster": "End-to-end research agents",
                                    "sota_investigation_mission": "Find recent autonomous research systems before the cutoff.",
                                    "limitation_hypothesis": "These systems are tightly coupled to internal experimentation loops.",
                                    "limitation_search_queries": [
                                        "autonomous research agent manuscript generation",
                                        "paper writing coupled to experiment pipeline"
                                    ],
                                    "bridge_to_our_method": "The proposed pipeline decouples writing from experimentation and grounds citations via verification."
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
                                        "Explain the inputs and generated artifact flow."
                                    ],
                                    "citation_hints": [
                                        "research paper or technical report introducing 'Semantic Scholar API'"
                                    ],
                                }
                            ],
                        }
                    ],
                }
                return json.dumps(payload, indent=2)
            if ("reviewer" in system or "overall_score" in system) and "reviewer_feedback" not in system:
                paper_text = request.user_prompt.lower()
                score = 72
                if "refined mock paper" in paper_text:
                    score = 78
                if "regressed mock paper" in paper_text:
                    score = 61
                payload = {
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
                        "critical_analysis_and_synthesis": {"score": max(score - 4, 0), "justification": "Synthesis is acceptable in the mock path."},
                        "positioning_and_novelty": {"score": max(score - 5, 0), "justification": "Positioning is acceptable in the mock path."},
                        "organization_and_writing": {"score": score, "justification": "Organization is acceptable in the mock path."},
                        "citation_practices_and_rigor": {"score": max(score - 3, 0), "justification": "Citation rigor is acceptable in the mock path."},
                    },
                    "penalties": [],
                    "summary": {
                        "strengths": ["Grounded artifact use"],
                        "weaknesses": ["Needs stronger synthesis"],
                        "top_improvements": ["Clarify literature positioning"]
                    },
                    "overall_score": score,
                    "questions": ["Clarify why the pipeline is decoupled from experiment generation."],
                }
                return json.dumps(payload, indent=2)
            payload = {"ok": True}
            return json.dumps(payload, indent=2)

        return self._mock_latex_document(request, refined=False)

    def fork(self) -> "MockProvider":
        return MockProvider()
