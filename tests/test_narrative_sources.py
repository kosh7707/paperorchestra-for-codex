from __future__ import annotations

from pathlib import Path

from paperorchestra.manuscript import narrative_sources


def test_planning_source_text_strips_comments_but_can_preserve_numeric_percent() -> None:
    text = "Claim keeps 95% recall % inline comment\nVisible % hidden\nEscaped \\% percent"

    stripped = narrative_sources._planning_source_text(text)
    preserved = narrative_sources._planning_source_text(text, preserve_numeric_percent=True)

    assert "inline comment" not in stripped
    assert "95%" not in stripped
    assert "95% recall" in preserved
    assert "Visible" in stripped
    assert "hidden" not in stripped
    assert "Escaped \\% percent" in stripped


def test_anchor_reports_hash_and_line_span(tmp_path: Path) -> None:
    source = tmp_path / "idea.md"
    source.write_text("First line\nEvidence lives here\nLast line\n", encoding="utf-8")

    anchor = narrative_sources._anchor(source, "Evidence lives here")

    assert anchor["source_ref"] == str(source)
    assert anchor["source_sha256"] == narrative_sources.file_sha256(source)
    assert anchor["evidence_excerpt"] == "Evidence lives here"
    assert anchor["line_start"] == 2
    assert anchor["line_end"] == 2


def test_plain_section_title_and_salient_terms_are_stable() -> None:
    assert narrative_sources._plain_section_title(r"\section*{Method}") == "Method"
    assert narrative_sources._plain_section_title("Plain") == "Plain"
    assert narrative_sources._salient_terms("PaperOrchestra reports 1.5x speedup for CodeQL triage", limit=3) == [
        "reports",
        "1.5x",
        "speedup",
    ]
