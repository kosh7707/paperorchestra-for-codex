from __future__ import annotations

from paperorchestra.manuscript import figure_matching
from paperorchestra.manuscript.figure_review_builder import build_figure_placement_review


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

    review = build_figure_placement_review(
        latex,
        plot_assets_index={"assets": [{"figure_id": "bench", "filename": "bench.pdf"}]},
        plot_manifest={"figures": [{"figure_id": "bench", "purpose": "Precision recall benchmark results"}]},
    )

    assert review["status"] == "fail"
    assert "figure_caption_plot_purpose_mismatch" in review["failing_codes"]
    assert review["figures"][0]["plot_manifest_match"]["figure_id"] == "bench"


def test_build_figure_placement_review_records_source_origin() -> None:
    source_latex = r"""
\section{Method}
\begin{figure}[t]
\includegraphics{pipeline.pdf}
\caption{Pipeline overview.}
\label{fig:pipeline}
\end{figure}
"""
    latex = r"""
\section{Method}
Figure~\ref{fig:pipeline} explains the preserved source figure.
\begin{figure}[t]
\includegraphics{pipeline.pdf}
\caption{Pipeline overview.}
\label{fig:pipeline}
\end{figure}
"""

    review = build_figure_placement_review(
        latex,
        source_latex=source_latex,
    )

    assert review["summary"]["figure_count"] == 1
    assert review["figures"][0]["source_origin"] == "source_preserved"


def test_build_figure_placement_review_records_tail_clump_for_each_late_figure() -> None:
    latex = r"""
\section{Method}
Figure~\ref{fig:pipeline} explains the preserved source figure.
\begin{figure}[t]
\includegraphics{pipeline.pdf}
\caption{Pipeline overview.}
\label{fig:pipeline}
\end{figure}
\section{Discussion}
Discussion filler.






\begin{figure}[t]
\includegraphics{late-a.pdf}
\caption{Late A.}
\label{fig:late-a}
\end{figure}
\begin{figure}[t]
\includegraphics{late-b.pdf}
\caption{Late B.}
\label{fig:late-b}
\end{figure}
"""

    review = build_figure_placement_review(
        latex,
        tail_ratio_threshold=0.5,
    )

    assert review["status"] == "warn"
    assert "tail_clump" in review["warning_codes"]
    assert review["summary"]["figure_count"] == 3
    assert review["figures"][1]["source_origin"] == "model_written"
    assert review["figures"][1]["warning_codes"].count("tail_clump") == 1
    assert review["figures"][2]["warning_codes"].count("tail_clump") == 1
    assert sum(1 for warning in review["warnings"] if warning["code"] == "tail_clump") == 2


def test_build_figure_placement_review_marks_auto_repaired_origin() -> None:
    latex = r"""
\section{Method}
% PaperOrchestra:auto-repaired
\begin{figure}[t]
\includegraphics{auto.pdf}
\caption{Auto repaired figure.}
\label{fig:auto}
\end{figure}
"""

    review = build_figure_placement_review(latex)

    assert review["figures"][0]["source_origin"] == "auto_repaired"
