from __future__ import annotations

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.engine.section_scope import (
    _expected_section_titles_from_outline,
    _filter_section_scoped_issues,
    _normalize_section_selection,
    _preserve_all_except_sections,
    _resolve_selected_sections,
    _selected_section_template,
)
from paperorchestra.manuscript.validation_types import ValidationIssue


SOURCE = """\\documentclass{llncs}
\\begin{document}
\\section{Introduction}
old intro
\\section{Method}
old method
\\section{Experiments}
old experiments
\\end{document}
"""

GENERATED = SOURCE.replace("old intro", "new intro").replace("old method", "new method").replace("old experiments", "new experiments")


def test_normalize_and_resolve_section_selection() -> None:
    assert _normalize_section_selection(" Introduction, Method;\nExperiments ") == ["Introduction", "Method", "Experiments"]
    assert _normalize_section_selection([" Method ", "", "Experiments"]) == ["Method", "Experiments"]
    assert _resolve_selected_sections(SOURCE, ["Method", "Experiments"]) == ["Method", "Experiments"]
    with pytest.raises(ContractError, match="Unknown section"):
        _resolve_selected_sections(SOURCE, ["Related Work"])


def test_preserve_all_except_sections_keeps_unrewritten_source_blocks() -> None:
    merged = _preserve_all_except_sections(GENERATED, SOURCE, rewritten_section_names=["Method"])

    assert "old intro" in merged
    assert "new method" in merged
    assert "old experiments" in merged
    assert "new intro" not in merged
    assert "old method" not in merged


def test_selected_section_template_keeps_preamble_selected_blocks_and_end_document() -> None:
    template = _selected_section_template(SOURCE, ["Method"])

    assert template.startswith("\\documentclass{llncs}\n\\begin{document}\n")
    assert "\\section{Method}" in template
    assert "old method" in template
    assert "old intro" not in template
    assert template.endswith("\\end{document}\n")


def test_filter_section_scoped_issues_drops_global_and_off_scope_numeric_issues() -> None:
    issues = [
        ValidationIssue("citation_coverage_insufficient", "error", "global citation coverage"),
        ValidationIssue("numeric_grounding_mismatch", "error", "numeric mismatch"),
        ValidationIssue("other", "warning", "other issue"),
    ]

    assert [issue.code for issue in _filter_section_scoped_issues(issues, selected_sections=["Method"])] == ["other"]
    assert [issue.code for issue in _filter_section_scoped_issues(issues, selected_sections=["Experiments"])] == [
        "numeric_grounding_mismatch",
        "other",
    ]
    assert _filter_section_scoped_issues(issues, selected_sections=[]) is issues


def test_expected_section_titles_from_outline_ignores_control_sections_and_adds_discussion_for_material_packets() -> None:
    outline = {
        "section_plan": [
            {"section_title": "Abstract"},
            {"section_title": "Proposed Method"},
            {"section_title": "Implementation and Results"},
            {"section_title": "Cross-cutting Citation Coverage Checklist"},
            {"section_title": "Author notes for positioning and framing"},
            {"section_title": "Related Work"},
        ]
    }

    assert _expected_section_titles_from_outline(outline) == ["method", "experiments", "Related Work", "Discussion"]


def test_expected_section_titles_accept_system_and_evaluation_aliases() -> None:
    outline = {
        "section_plan": [
            {"section_title": "System"},
            {"section_title": "Evaluation Design"},
            {"section_title": "Discussion and Limitations"},
        ]
    }

    assert _expected_section_titles_from_outline(outline) == ["method", "experiments", "discussion"]


def test_section_scope_resolves_and_preserves_canonical_aliases() -> None:
    source = r"""\documentclass{article}
\begin{document}
\section{Introduction}
old intro
\section{Methodology}
old method
\section{Experiment Setup}
old experiments
\end{document}
"""
    generated = source.replace("old intro", "new intro").replace("old method", "new method").replace("old experiments", "new experiments")

    assert _resolve_selected_sections(source, ["Method", "Experiments"]) == ["Methodology", "Experiment Setup"]
    template = _selected_section_template(source, ["Method", "Experiments"])
    assert "old method" in template
    assert "old experiments" in template
    assert "old intro" not in template

    merged = _preserve_all_except_sections(generated, source, rewritten_section_names=["Method"])
    assert "old intro" in merged
    assert "new method" in merged
    assert "old experiments" in merged
