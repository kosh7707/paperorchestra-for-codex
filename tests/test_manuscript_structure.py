from __future__ import annotations

from paperorchestra.manuscript.structure import (
    _canonical_generated_section_title,
    _insert_block_into_section,
    _normalized_section_range_map,
    _preferred_section_name,
    _section_range_map,
)


LATEX = """\\begin{document}
\\section{Introduction}
Intro cites Figure~\\ref{fig:main}.

More intro.
\\section{Method}
Method text mentions source finality.
\\section{Experiments}
Results text.
\\end{document}
"""


def test_section_range_map_stops_at_next_section_and_end_document() -> None:
    ranges = _section_range_map(LATEX)

    intro = LATEX[ranges["introduction"][0] : ranges["introduction"][1]]
    experiments = LATEX[ranges["experiments"][0] : ranges["experiments"][1]]
    assert intro.startswith("\\section{Introduction}")
    assert "\\section{Method}" not in intro
    assert experiments.endswith("Results text.\n")
    assert "\\end{document}" not in experiments


def test_canonical_and_normalized_section_titles() -> None:
    assert _canonical_generated_section_title("\\section{Proposed Method}") == "method"
    assert _canonical_generated_section_title("Implementation and Results") == "experiments"
    assert _canonical_generated_section_title("Discussion and Limitations") == "discussion"
    normalized = _normalized_section_range_map(LATEX.replace("Method", "Proposed Method"))
    assert "method" in normalized


def test_preferred_section_uses_reference_anchor_then_default_order() -> None:
    assert _preferred_section_name(LATEX, label="fig:main") == "introduction"
    assert _preferred_section_name(LATEX, anchor_tokens=["source finality"]) == "method"
    assert _preferred_section_name("\\section{Background}\nText") == "background"
    assert _preferred_section_name("no sections") is None


def test_insert_block_into_section_prefers_label_or_anchor_and_appends_for_unknown_section() -> None:
    by_label = _insert_block_into_section(LATEX, section_name="Introduction", label="fig:main", block="Inserted after ref.")
    assert by_label.index("Figure~\\ref{fig:main}.") < by_label.index("Inserted after ref.") < by_label.index("More intro")

    by_anchor = _insert_block_into_section(LATEX, section_name="Method", anchor_tokens=["source finality"], block="Inserted after anchor.")
    assert by_anchor.index("source finality.") < by_anchor.index("Inserted after anchor.") < by_anchor.index("\\section{Experiments}")

    appended = _insert_block_into_section(LATEX, section_name="Missing", block="Fallback append.")
    assert appended.endswith("\nFallback append.\n")
