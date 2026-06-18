from __future__ import annotations

from pathlib import Path

from paperorchestra.engine.latex_generated_plot_usage import _ensure_generated_plot_usage
from paperorchestra.engine.latex_plot_generated_paths import _normalize_generated_plot_paths
from paperorchestra.engine.latex_postprocess import _normalize_source_figure_paths, _stabilize_figure_float_placement


def test_generated_plot_usage_inserts_reviewable_asset_into_preferred_section() -> None:
    latex = "\\section{Method}\nText about triage pipeline.\n\\section{Results}\n"
    rendered = _ensure_generated_plot_usage(
        latex,
        {
            "assets": [
                {
                    "figure_id": "fig:triage_pipeline",
                    "title": "Triage Pipeline",
                    "caption": "Triage pipeline & evidence",
                    "latex_snippet_path": "build/plot-assets/triage.tex",
                }
            ]
        },
    )

    assert "% PaperOrchestra:auto-repaired figure:fig:triage_pipeline" in rendered
    assert "\\input{build/plot-assets/triage.tex}" in rendered
    assert "\\caption{Triage pipeline \\& evidence}" in rendered
    assert rendered.index("\\section{Method}") < rendered.index("\\label{fig:triage_pipeline}") < rendered.index("\\section{Results}")


def test_generated_plot_path_normalization_rewrites_matching_figure_block() -> None:
    latex = """\\begin{figure}[t]
\\includegraphics[width=\\linewidth]{old/path/pipeline.pdf}
\\caption{Pipeline}
\\label{fig:pipeline}
\\end{figure}
"""
    rendered = _normalize_generated_plot_paths(
        latex,
        {"assets": [{"figure_id": "fig:pipeline", "latex_snippet_path": "build/plot-assets/pipeline.tex", "filename": "pipeline.pdf"}]},
    )

    assert "\\input{build/plot-assets/pipeline.tex}" in rendered
    assert "old/path/pipeline.pdf" not in rendered


def test_source_figure_paths_and_float_placement_are_stabilized(tmp_path: Path) -> None:
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "source.png").write_bytes(b"png")

    normalized = _normalize_source_figure_paths(
        "\\begin{figure}\\includegraphics{figures/source.png}\\end{figure}",
        str(figures),
    )
    stabilized = _stabilize_figure_float_placement(normalized)

    assert "inputs/figures/source.png" in stabilized
    assert "\\begin{figure}[!htbp]" in stabilized
