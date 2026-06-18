from __future__ import annotations

from paperorchestra.manuscript import labels, repair


def test_remove_material_packet_sections_preserves_macros_in_preamble() -> None:
    latex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\section{00 Core Macros}\n"
        "\\newcommand{\\ToolName}{PaperOrchestra}\n"
        "\\section{Introduction}\n"
        "We use \\ToolName.\n"
        "\\end{document}\n"
    )

    repaired = repair._remove_material_packet_sections(latex)

    assert "\\section{00 Core Macros}" not in repaired
    assert repaired.index("\\newcommand{\\ToolName}") < repaired.index("\\begin{document}")
    assert "\\section{Introduction}" in repaired


def test_restore_missing_referenced_labels_from_template_and_common_sections() -> None:
    generated = (
        "\\section{Method}\n"
        "See Section~\\ref{sec:method} and Section~\\ref{subsec:detail}.\n"
        "\\subsection{Details}\n"
        "Details.\n"
    )
    template = (
        "\\section{Method}\n"
        "\\subsection{Original Details}\n"
        "\\label{subsec:detail}\n"
        "Source detail.\n"
    )

    repaired = labels._restore_missing_referenced_labels(generated, template)

    assert "\\label{sec:method}" in repaired
    assert "\\label{subsec:detail}" in repaired


def test_citation_map_for_selected_sections_filters_to_local_citations() -> None:
    latex = (
        "\\section{Introduction}\n"
        "Intro claim \\cite{A}.\n"
        "\\section{Method}\n"
        "Method claim \\cite{B}.\n"
    )
    citation_map = {
        "A": {"title": "Intro Paper"},
        "B": {"title": "Method Paper"},
    }

    subset = repair._citation_map_for_selected_sections(latex, citation_map, ["Method"])

    assert subset == {"B": {"title": "Method Paper"}}


def test_control_prose_sanitizer_normalizes_portable_citations_and_packet_language() -> None:
    latex = r"The supplied packet follows \citet[see][p. 2]{smith2024}."

    repaired = repair._sanitize_manuscript_control_prose(latex)

    assert "stated evidence" in repaired
    assert r"\cite{smith2024}" in repaired
