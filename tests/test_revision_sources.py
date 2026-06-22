from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.manuscript import revisions
from paperorchestra.manuscript.revision_review_findings import _iter_review_findings
from paperorchestra.manuscript.revision_source_files import _section_diagnostics, _section_files


def test_review_findings_collect_summary_questions_penalties_and_low_axes() -> None:
    review = {
        "summary": {"weaknesses": ["Weak intro"], "top_improvements": ["Add threat model"]},
        "questions": ["Why this benchmark?"],
        "penalties": [{"reason": "Missing limitation"}],
        "axis_scores": {"clarity": {"score": 55, "justification": "Hard to follow"}, "novelty": {"score": 80}},
    }

    findings = _iter_review_findings(review)

    assert [finding["source"] for finding in findings] == [
        "summary.weaknesses",
        "summary.top_improvements",
        "questions",
        "penalties",
        "axis_scores.clarity",
    ]
    assert findings[-1]["text"] == "Hard to follow"


def test_section_files_and_diagnostics_map_included_tex_files(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    intro = tmp_path / "intro_related.tex"
    method = tmp_path / "method.tex"
    paper.write_text(r"\input{intro_related}\n\include{method}", encoding="utf-8")
    intro.write_text(r"Intro words \cite{A}. TODO", encoding="utf-8")
    method.write_text("Method words.", encoding="utf-8")

    section_map = _section_files(paper)
    diagnostics = _section_diagnostics(section_map)

    assert section_map["introduction_related_work"] == str(intro)
    assert section_map["proposed_method"] == str(method)
    assert diagnostics["introduction_related_work"]["citation_count"] == 1
    assert diagnostics["introduction_related_work"]["todo_markers"] == 1


def test_revision_suggestions_include_section_and_citation_findings(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    review = tmp_path / "review.json"
    section_review = tmp_path / "section.json"
    citation_review = tmp_path / "citation.json"
    paper.write_text("Body", encoding="utf-8")
    review.write_text(json.dumps({"summary": {"weaknesses": ["Clarify method"]}}), encoding="utf-8")
    section_review.write_text(
        json.dumps({"sections": [{"section_title": "Method", "required_fixes": ["Explain pipeline"]}]}),
        encoding="utf-8",
    )
    citation_review.write_text(
        json.dumps({"items": [{"id": "c1", "support_status": "unsupported", "sentence": "Claim", "suggested_fix": "Verify source"}]}),
        encoding="utf-8",
    )

    payload = revisions.build_revision_suggestions(
        paper,
        review,
        section_review_json=section_review,
        citation_review_json=citation_review,
    )

    assert payload["action_count"] == 3
    assert any(action["action_type"] == "curate_and_verify_citations" for action in payload["actions"])
    assert all(action["repair_class"] == "contract_internal_repair" for action in payload["actions"])
    assert all("contract_refs" in action for action in payload["actions"])
