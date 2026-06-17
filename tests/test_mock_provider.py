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
    assert "\\input{figures/custom.tex}" in latex
    assert "12.5" in latex


def test_mock_provider_fork_returns_independent_mock_provider() -> None:
    provider = MockProvider()

    forked = provider.fork()

    assert isinstance(forked, MockProvider)
    assert forked is not provider
