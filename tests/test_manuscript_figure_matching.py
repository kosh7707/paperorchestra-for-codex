from __future__ import annotations

from paperorchestra.manuscript import figure_matching, figure_patterns, figure_validation


def test_figure_validation_facade_reexports_patterns_and_matching_helpers() -> None:
    assert "build_figure_placement_review" in figure_validation.__all__
    assert "_match_plot_manifest" in figure_validation.__all__
    assert figure_validation.FIGURE_ENV_RE is figure_patterns.FIGURE_ENV_RE
    assert figure_validation.CAPTION_RE is figure_patterns.CAPTION_RE
    assert figure_validation.REF_RE is figure_patterns.REF_RE
    assert figure_validation.LABEL_RE is figure_patterns.LABEL_RE
    assert figure_validation.INCLUDE_GRAPHICS_RE is figure_patterns.INCLUDE_GRAPHICS_RE
    assert figure_validation.NONTECHNICAL_VISUAL_STRONG_RE is figure_patterns.NONTECHNICAL_VISUAL_STRONG_RE
    assert figure_validation.NONTECHNICAL_VISUAL_CONTEXT_RE is figure_patterns.NONTECHNICAL_VISUAL_CONTEXT_RE
    assert figure_validation.DECORATIVE_VISUAL_RE is figure_patterns.DECORATIVE_VISUAL_RE
    assert figure_validation.PROCESS_CAPTION_RE is figure_patterns.PROCESS_CAPTION_RE
    assert figure_validation.UNRELATED_CAPTION_CUE_RE is figure_patterns.UNRELATED_CAPTION_CUE_RE
    assert figure_matching._NONTECHNICAL_VISUAL_STRONG_RE is figure_patterns.NONTECHNICAL_VISUAL_STRONG_RE
    assert figure_matching._NONTECHNICAL_VISUAL_CONTEXT_RE is figure_patterns.NONTECHNICAL_VISUAL_CONTEXT_RE
    assert figure_matching._DECORATIVE_VISUAL_RE is figure_patterns.DECORATIVE_VISUAL_RE
    assert figure_matching._PROCESS_CAPTION_RE is figure_patterns.PROCESS_CAPTION_RE
    assert figure_matching._UNRELATED_CAPTION_CUE_RE is figure_patterns.UNRELATED_CAPTION_CUE_RE
    assert figure_validation._normalize_figure_key is figure_matching._normalize_figure_key
    assert figure_validation._high_signal_tokens is figure_matching._high_signal_tokens
    assert figure_validation._plot_asset_candidates is figure_matching._plot_asset_candidates
    assert figure_validation._plot_manifest_candidates is figure_matching._plot_manifest_candidates
    assert figure_validation._asset_is_reviewable is figure_matching._asset_is_reviewable
    assert figure_validation._figure_keys is figure_matching._figure_keys
    assert figure_validation._match_plot_manifest is figure_matching._match_plot_manifest
    assert figure_validation._caption_manifest_relation is figure_matching._caption_manifest_relation
    assert figure_validation._included_asset_names is figure_matching._included_asset_names
    assert figure_validation._body_figure_has_nontechnical_asset is figure_matching._body_figure_has_nontechnical_asset
    assert figure_validation._caption_has_process_or_placeholder_text is figure_matching._caption_has_process_or_placeholder_text


def test_match_plot_manifest_prefers_asset_and_marks_placeholder_unreviewable() -> None:
    plot_assets_index = {
        "assets": [
            {
                "figure_id": "pipeline",
                "filename": "pipeline-overview.pdf",
                "asset_kind": "generated_placeholder",
                "review_status": "human_final_artwork_required",
            }
        ]
    }
    plot_manifest = {"figures": [{"figure_id": "pipeline", "purpose": "Pipeline overview"}]}

    match = figure_matching._match_plot_manifest(
        label="fig:other",
        caption="Unrelated caption",
        included_assets=["pipeline-overview.pdf"],
        plot_manifest=plot_manifest,
        plot_assets_index=plot_assets_index,
    )

    assert match is not None
    assert match["status"] == "matched"
    assert match["match_precedence"] == "asset"
    assert match["figure_id"] == "pipeline"
    assert match["reviewable"] is False
    assert match["asset"]["review_status"] == "human_final_artwork_required"


def test_caption_manifest_relation_detects_process_caption_mismatch() -> None:
    relation = figure_matching._caption_manifest_relation(
        "Placeholder figure prompt showing author workflow.",
        {
            "status": "matched",
            "reviewable": True,
            "purpose": "Precision recall benchmark results",
            "title": "Benchmark results",
            "caption": "Precision and recall by CWE",
            "figure_id": "benchmark",
        },
    )

    assert relation == "mismatch"


def test_body_helpers_detect_nontechnical_and_placeholder_text() -> None:
    body = r"\\includegraphics{assets/author-headshot.png}"

    assert figure_matching._included_asset_names(body) == ["assets/author-headshot.png"]
    assert figure_matching._body_figure_has_nontechnical_asset(body, "Author profile photo") is True
    assert figure_matching._caption_has_process_or_placeholder_text("Placeholder figure caption intent") is True


def test_build_figure_placement_review_uses_manifest_matching_helpers() -> None:
    latex = r"""
\section{Method}
Figure~\ref{fig:bench} summarizes benchmark results.
\begin{figure}[t]
\includegraphics{bench.pdf}
\caption{Placeholder figure prompt showing author workflow.}
\label{fig:bench}
\end{figure}
"""

    review = figure_validation.build_figure_placement_review(
        latex,
        plot_assets_index={"assets": [{"figure_id": "bench", "filename": "bench.pdf"}]},
        plot_manifest={"figures": [{"figure_id": "bench", "purpose": "Precision recall benchmark results"}]},
    )

    assert review["status"] == "fail"
    assert "figure_caption_plot_purpose_mismatch" in review["failing_codes"]
    assert review["figures"][0]["plot_manifest_match"]["figure_id"] == "bench"
