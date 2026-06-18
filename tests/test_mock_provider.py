from __future__ import annotations

import json

from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.provider_base import CompletionRequest


def test_mock_provider_generates_prior_work_seed_json() -> None:
    provider = MockProvider()

    response = provider.complete(
        CompletionRequest(
            system_prompt="You are a prior-work seed generator.",
            user_prompt="Generate seeds.",
        )
    )

    payload = json.loads(response)
    assert "references" in payload
    assert payload["references"]
    assert payload["research_notes"] == ["Mock provider returns canonical seed examples without live web access."]


def test_mock_provider_citation_support_verifier_returns_manual_checks() -> None:
    provider = MockProvider()

    response = provider.complete(
        CompletionRequest(
            system_prompt="You are PaperOrchestra's citation-support verifier.",
            user_prompt='{"items":[{"id":"cite-1"},{"id":"cite-2"}]}',
        )
    )

    payload = json.loads(response)
    assert [item["id"] for item in payload["items"]] == ["cite-1", "cite-2"]
    assert {item["support_status"] for item in payload["items"]} == {"needs_manual_check"}
    assert payload["research_notes"] == ["Mock provider does not claim cited-sentence support."]


def test_mock_provider_latex_uses_prompt_citations_and_plot_assets() -> None:
    provider = MockProvider()

    latex = provider.complete(
        CompletionRequest(
            system_prompt="Write a paper.",
            user_prompt="""
<DATA_BLOCK name="citation_checklist">
["alpha2024", "beta2025"]
</DATA_BLOCK>
<DATA_BLOCK name="plot_manifest.json">
{"figures":[{"figure_id":"fig_custom"}]}
</DATA_BLOCK>
<DATA_BLOCK name="plot_assets.json">
{"assets":[{"latex_snippet_path":"figures/custom.tex"}]}
</DATA_BLOCK>
<DATA_BLOCK name="experimental_log.md">
Precision: 12.5%
</DATA_BLOCK>
""",
        )
    )

    assert "\\cite{alpha2024,beta2025}" in latex
    assert "\\label{fig_custom}" in latex
    assert "\n\\input{figures/custom.tex}\n\n\\caption{Overview of the staged pipeline.}" in latex
    assert "12.5" in latex


def test_mock_provider_latex_preserves_default_figure_block_spacing() -> None:
    provider = MockProvider()

    latex = provider.complete(CompletionRequest(system_prompt="Write a paper.", user_prompt="No assets."))

    assert "\n\\begin{figure}\n\n\\caption{Overview of the staged pipeline.}" in latex


def test_mock_provider_latex_uses_non_tex_plot_asset_with_original_spacing() -> None:
    provider = MockProvider()

    latex = provider.complete(
        CompletionRequest(
            system_prompt="Write a paper.",
            user_prompt="""
<DATA_BLOCK name="plot_assets.json">
{"assets":[{"filename":"figures/custom.png"}]}
</DATA_BLOCK>
""",
        )
    )

    assert "\n\\includegraphics[width=0.85\\linewidth]{figures/custom.png}\n\n\\caption" in latex


def test_mock_provider_generates_outline_json() -> None:
    provider = MockProvider()

    response = provider.complete(
        CompletionRequest(
            system_prompt="Return a single, valid JSON object containing plotting_plan and outline.",
            user_prompt="Plan the paper.",
        )
    )

    payload = json.loads(response)
    assert payload["plotting_plan"][0]["figure_id"] == "fig_framework_overview"
    assert "intro_related_work_plan" in payload
    assert payload["section_plan"][0]["section_title"] == "Method"


def test_mock_provider_generates_figure_json() -> None:
    provider = MockProvider()

    response = provider.complete(
        CompletionRequest(
            system_prompt="Return a single, valid JSON object with a top-level key named figures.",
            user_prompt="Plan figures.",
        )
    )

    payload = json.loads(response)
    assert payload["figures"][0]["figure_id"] == "fig_framework_overview"
    assert payload["figures"][0]["plot_type"] == "diagram"


def test_mock_provider_reviewer_score_tracks_refined_and_regressed_markers() -> None:
    provider = MockProvider()

    refined = json.loads(
        provider.complete(
            CompletionRequest(
                system_prompt="Return a JSON object with reviewer overall_score.",
                user_prompt="Refined mock paper",
            )
        )
    )
    regressed = json.loads(
        provider.complete(
            CompletionRequest(
                system_prompt="Return a JSON object with reviewer overall_score.",
                user_prompt="Regressed mock paper",
            )
        )
    )

    assert refined["overall_score"] == 78
    assert regressed["overall_score"] == 61


def test_mock_provider_refinement_response_contains_worklog_and_refined_latex() -> None:
    provider = MockProvider()

    response = provider.complete(
        CompletionRequest(
            system_prompt="You are a content refinement agent that returns two fenced code blocks.",
            user_prompt="Improve draft.",
        )
    )

    assert '"addressed_weaknesses"' in response
    assert "Refined mock paper." in response
    assert "\\section{Introduction}" in response


def test_mock_provider_fork_returns_independent_mock_provider() -> None:
    provider = MockProvider()

    forked = provider.fork()

    assert isinstance(forked, MockProvider)
    assert forked is not provider
