from __future__ import annotations

from paperorchestra.manuscript import repair


def _claim(*, target: str = "Discussion", note: str = "Claims stay within measured evidence") -> dict[str, object]:
    return {
        "id": "c1",
        "target_section": target,
        "required": True,
        "scope_note": note,
    }


def test_discussion_boundary_claim_inserts_section_before_conclusion() -> None:
    latex = (
        "\\section{Introduction}\n"
        "Intro.\n"
        "\\section{Conclusion}\n"
        "Done.\n"
        "\\end{document}\n"
    )

    repaired = repair._ensure_discussion_section_for_claim_boundaries(latex, {"claims": [_claim()]})

    assert repaired.index("\\section{Discussion}") < repaired.index("\\section{Conclusion}")
    assert "Claims stay within measured evidence." in repaired
    assert repaired.count("Claims stay within measured evidence.") == 1


def test_discussion_boundary_claim_does_not_duplicate_existing_note() -> None:
    latex = (
        "\\section{Discussion}\n"
        "Claims stay within measured evidence.\n\n"
        "\\section{Conclusion}\n"
        "Done.\n"
    )

    repaired = repair._ensure_discussion_section_for_claim_boundaries(latex, {"claims": [_claim()]})

    assert repaired == latex


def test_required_claim_scope_note_is_inserted_in_target_section_once() -> None:
    latex = (
        "\\section{Method}\n"
        "Method body.\n"
        "\\section{Evaluation}\n"
        "Numbers.\n"
    )

    once = repair._ensure_required_claim_scope_notes(
        latex,
        {"claims": [_claim(target="Evaluation", note="Evaluation claims are limited to the frozen run")]},
    )
    twice = repair._ensure_required_claim_scope_notes(
        once,
        {"claims": [_claim(target="Evaluation", note="Evaluation claims are limited to the frozen run")]},
    )

    assert once.index("Evaluation claims are limited to the frozen run.") < once.index("Numbers.")
    assert twice.count("Evaluation claims are limited to the frozen run.") == 1


def test_citation_map_for_selected_sections_uses_canonical_keys_and_full_fallback() -> None:
    latex = (
        "\\section{Introduction}\n"
        "Intro claim \\cite{AliasA}.\n"
        "\\section{Method}\n"
        "Method claim \\cite{B}.\n"
        "\\section{Conclusion}\n"
        "No local citations.\n"
    )
    citation_map = {
        "AliasA": {"title": "Intro Paper", "canonical_bibtex_key": "A"},
        "B": {"title": "Method Paper"},
    }

    intro_subset = repair._citation_map_for_selected_sections(latex, citation_map, ["Introduction"])
    full_fallback = repair._citation_map_for_selected_sections(latex, citation_map, ["Conclusion"])

    assert intro_subset == {"A": {"title": "Intro Paper", "canonical_bibtex_key": "A"}}
    assert full_fallback == {
        "A": {"title": "Intro Paper", "canonical_bibtex_key": "A"},
        "B": {"title": "Method Paper"},
    }
