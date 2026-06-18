from __future__ import annotations

from paperorchestra.engine import latex_plot_context as context


def test_normalize_plot_context_key_strips_figure_prefix_path_and_extension() -> None:
    assert context._normalize_plot_context_key("Fig: Results-Overview.pdf") == "resultsoverview"
    assert context._normalize_plot_context_key("plots/fig:Pipeline_v2.tex") == "figpipelinev2"


def test_reviewable_plot_context_removes_generated_placeholders() -> None:
    assets = {
        "assets": [
            {"figure_id": "fig:real", "filename": "real.pdf"},
            {"figure_id": "fig:placeholder", "asset_kind": "generated_placeholder"},
            {"figure_id": "fig:human", "review_status": "human_final_artwork_required"},
        ],
        "other": "kept",
    }
    manifest = {
        "figures": [
            {"figure_id": "fig:real", "title": "Real"},
            {"figure_id": "fig:placeholder", "title": "Placeholder"},
            {"figure_id": "fig:human", "title": "Human"},
        ]
    }

    reviewable_assets = context._reviewable_plot_assets_index(assets)
    reviewable_manifest = context._reviewable_plot_manifest(manifest, assets)

    assert reviewable_assets == {"assets": [{"figure_id": "fig:real", "filename": "real.pdf"}], "other": "kept"}
    assert reviewable_manifest == {"figures": [{"figure_id": "fig:real", "title": "Real"}]}


def test_filter_plot_context_for_latex_keeps_included_assets_and_referenced_figures() -> None:
    latex = r"""
\section{Results}
See \cref{fig:kept}.
\begin{figure}
\includegraphics{build/plots/included.pdf}
\label{fig:included}
\end{figure}
"""
    manifest = {
        "figures": [
            {"figure_id": "fig:kept"},
            {"figure_id": "fig:included"},
            {"figure_id": "fig:unused"},
        ]
    }
    assets = {
        "assets": [
            {"figure_id": "fig:included", "filename": "included.pdf"},
            {"figure_id": "fig:unused", "filename": "unused.pdf"},
        ]
    }

    scoped_manifest, scoped_assets = context._filter_plot_context_for_latex(latex, manifest, assets)

    assert scoped_assets["assets"] == [{"figure_id": "fig:included", "filename": "included.pdf"}]
    assert scoped_manifest["figures"] == [{"figure_id": "fig:kept"}, {"figure_id": "fig:included"}]
