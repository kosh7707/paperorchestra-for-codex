from __future__ import annotations

from types import SimpleNamespace

from paperorchestra.core.io import write_json
from paperorchestra.core.session import set_current_session
from paperorchestra.loop_engine.quality.section_quality_check import _section_quality_check


def _state(paper_path, review_path):
    return SimpleNamespace(
        artifacts=SimpleNamespace(
            latest_section_review_json=str(review_path),
            paper_full_tex=str(paper_path),
        )
    )


def test_section_quality_check_flags_low_required_fix_and_process_residue(tmp_path) -> None:
    set_current_session(tmp_path, "po-section-quality")
    paper = tmp_path / "paper.tex"
    paper.write_text("paper", encoding="utf-8")
    review = tmp_path / "section_review.json"
    from paperorchestra.loop_engine.quality.utils import _file_sha256

    write_json(
        review,
        {
            "schema_version": "section-review/1",
            "manuscript_sha256": _file_sha256(paper),
            "overall_section_score": 90,
            "score_use": "advisory",
            "sections": [
                {"section_title": "Intro", "score": 20, "verdict": "major_revision", "required_fixes": ["rewrite"]},
                {"section_title": "Method", "score": 95, "verdict": "ok", "required_fixes": ["clarify"]},
                {"section_title": "Results", "score": 95, "verdict": "ok", "process_residue_markers": ["TODO"]},
            ],
        },
    )

    payload = _section_quality_check(tmp_path, _state(paper, review), quality_mode="claim_safe")

    assert payload["status"] == "fail"
    assert payload["failing_codes"] == [
        "section_process_residue_detected",
        "section_quality_below_threshold",
        "section_required_fixes_pending",
    ]
    assert payload["low_sections"][0]["section_title"] == "Intro"
    assert payload["sections_with_required_fixes"][0]["section_title"] == "Method"
    assert payload["sections_with_process_residue"][0] == {"section_title": "Results", "markers": ["TODO"]}
    assert payload["load_bearing"] is False


def test_section_quality_check_rejects_stale_or_legacy_review(tmp_path) -> None:
    set_current_session(tmp_path, "po-section-quality-stale")
    paper = tmp_path / "paper.tex"
    paper.write_text("paper", encoding="utf-8")
    review = tmp_path / "section_review.json"

    write_json(review, {"schema_version": "legacy", "overall_section_score": 80})
    legacy = _section_quality_check(tmp_path, _state(paper, review), quality_mode="claim_safe")
    assert legacy["failing_codes"] == ["section_review_legacy_untrusted"]

    write_json(review, {"schema_version": "section-review/1", "manuscript_sha256": "stale", "overall_section_score": 80})
    stale = _section_quality_check(tmp_path, _state(paper, review), quality_mode="claim_safe")
    assert stale["failing_codes"] == ["section_review_stale"]
    assert stale["actual_manuscript_sha256"] == "stale"


def test_write_section_review_records_current_manuscript_hash(tmp_path) -> None:
    from paperorchestra.core.io import read_json
    from paperorchestra.core.models import InputBundle
    from paperorchestra.core.session import create_session, load_session, save_session
    from paperorchestra.loop_engine.quality.utils import _file_sha256
    from paperorchestra.reviews.section_review import write_section_review

    def write(name: str, text: str) -> str:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=write("idea.md", "idea"),
            experimental_log_path=write("experiment.md", "experiment"),
            template_path=write("template.tex", "\\documentclass{article}"),
            guidelines_path=write("guidelines.md", "guidelines"),
        ),
    )
    paper = tmp_path / "paper.tex"
    paper.write_text(
        "\\documentclass{article}\\begin{document}\\section{Introduction} "
        + "This section discusses evidence grounded triage. " * 12
        + "\\end{document}",
        encoding="utf-8",
    )
    state.artifacts.paper_full_tex = str(paper)
    save_session(tmp_path, state)

    review_path = write_section_review(tmp_path, tmp_path / "section_review.json")
    payload = read_json(review_path)
    refreshed = load_session(tmp_path)

    assert payload["manuscript_sha256"] == _file_sha256(paper)
    assert refreshed.artifacts.latest_section_review_json == str(review_path.resolve())
