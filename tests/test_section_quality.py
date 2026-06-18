from __future__ import annotations

from types import SimpleNamespace

from paperorchestra.core.io import write_json
from paperorchestra.core.session import set_current_session
from paperorchestra.loop_engine.quality import section_quality


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

    payload = section_quality._section_quality_check(tmp_path, _state(paper, review), quality_mode="claim_safe")

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
    legacy = section_quality._section_quality_check(tmp_path, _state(paper, review), quality_mode="claim_safe")
    assert legacy["failing_codes"] == ["section_review_legacy_untrusted"]

    write_json(review, {"schema_version": "section-review/1", "manuscript_sha256": "stale", "overall_section_score": 80})
    stale = section_quality._section_quality_check(tmp_path, _state(paper, review), quality_mode="claim_safe")
    assert stale["failing_codes"] == ["section_review_stale"]
    assert stale["actual_manuscript_sha256"] == "stale"
