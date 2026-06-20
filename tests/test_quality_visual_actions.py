from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.loop_engine.quality.action_families.visual_review_actions import _page_visual_review_actions
from paperorchestra.loop_engine.quality.policy import QA_LOOP_SUPPORTED_HANDLER_CODES
from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.loop_engine.ralph.action_dispatch_handlers import handled_action_codes


def _state(*, paper: Path, pdf: Path | None = None, review: Path | None = None, repair_brief: Path | None = None):
    return SimpleNamespace(
        artifacts=SimpleNamespace(
            paper_full_tex=str(paper),
            compiled_pdf=str(pdf) if pdf else None,
            latest_page_layout_review_json=str(review) if review else None,
            latest_visual_repair_brief_json=str(repair_brief) if repair_brief else None,
        )
    )


def test_page_visual_actions_request_audit_when_compiled_pdf_has_no_review(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    pdf = tmp_path / "paper.pdf"
    paper.write_text("body", encoding="utf-8")
    pdf.write_bytes(b"pdf")

    actions = _page_visual_review_actions(_state(paper=paper, pdf=pdf))

    assert [action["code"] for action in actions] == ["page_layout_review_missing"]
    assert actions[0]["automation"] == "automatic"
    assert "paperorchestra visual-audit" in actions[0]["suggested_commands"][0]


def test_page_visual_actions_request_refresh_for_stale_review(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    pdf = tmp_path / "paper.pdf"
    review = tmp_path / "page-layout-review.json"
    paper.write_text("new body", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    review.write_text(json.dumps({"manuscript_sha256": "old", "repair_candidates": []}), encoding="utf-8")

    actions = _page_visual_review_actions(_state(paper=paper, pdf=pdf, review=review))

    assert [action["code"] for action in actions] == ["page_layout_review_stale"]
    assert actions[0]["automation"] == "automatic"


def test_page_visual_actions_convert_findings_to_self_repair_brief_step(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    pdf = tmp_path / "paper.pdf"
    review = tmp_path / "page-layout-review.json"
    paper.write_text("body", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    review.write_text(
        json.dumps(
            {
                "manuscript_sha256": _file_sha256(paper),
                "compiled_pdf_sha256": _file_sha256(pdf),
                "repair_candidates": [
                    {
                        "code": "table_overflow",
                        "automation": "semi_auto",
                        "target": "Table 2",
                        "detail": "Right edge clipped.",
                        "suggested_fix": "Rewrite table layout.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    actions = _page_visual_review_actions(_state(paper=paper, pdf=pdf, review=review))

    assert [action["code"] for action in actions] == ["visual_layout_repair_brief_needed"]
    assert actions[0]["automation"] == "semi_auto"
    assert actions[0]["approval_required_from"] == "visual_layout_critic"
    assert "not the user" in actions[0]["ralph_instruction"].lower()


def test_page_visual_handler_codes_are_supported_by_qa_loop() -> None:
    expected = {
        "page_layout_review_missing",
        "page_layout_review_stale",
        "page_layout_render_failed",
        "page_layout_render_unavailable",
        "visual_layout_repair_brief_needed",
        "visual_layout_repair_candidate_needed",
    }

    assert expected <= QA_LOOP_SUPPORTED_HANDLER_CODES
    assert expected <= handled_action_codes()


def test_strict_page_layout_issues_fold_into_supported_repair_code(tmp_path: Path) -> None:
    from paperorchestra.reviews.reproducibility_strict_page_layout import _strict_page_layout_payload_issues

    review = tmp_path / "page-layout-review.json"
    issues = _strict_page_layout_payload_issues(
        review,
        {"warning_codes": ["visual_review_pending"], "failing_codes": ["table_overflow", "final_artwork_required"]},
    )

    assert [issue["code"] for issue in issues] == [
        "visual_layout_repair_brief_needed",
        "visual_final_artwork_handoff",
        "visual_layout_repair_brief_needed",
    ]
    assert issues[0]["source_finding_code"] == "table_overflow"
    assert issues[1]["kind"] == "page_layout_human"


def test_render_failure_keeps_dedicated_action_code(tmp_path: Path) -> None:
    from paperorchestra.reviews.reproducibility_strict_page_layout import _strict_page_layout_payload_issues

    review = tmp_path / "page-layout-review.json"
    issues = _strict_page_layout_payload_issues(review, {"render_status": {"status": "fail", "reason": "bad_pdf"}})

    assert [issue["code"] for issue in issues] == ["page_layout_render_failed"]
    assert issues[0]["source_finding_code"] == "visual_render_failed"


def test_page_visual_actions_keep_loop_alive_until_candidate_then_handoff(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    pdf = tmp_path / "paper.pdf"
    review = tmp_path / "page-layout-review.json"
    brief = tmp_path / "visual_repair_brief.json"
    candidate = tmp_path / "visual_repair_candidate.json"
    paper.write_text("body", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    review.write_text(
        json.dumps(
            {
                "manuscript_sha256": _file_sha256(paper),
                "compiled_pdf_sha256": _file_sha256(pdf),
                "render_status": {"status": "pass"},
                "repair_candidates": [{"code": "table_overflow", "automation": "semi_auto", "target": "Table 2"}],
            }
        ),
        encoding="utf-8",
    )

    first = _page_visual_review_actions(_state(paper=paper, pdf=pdf, review=review))
    assert [action["code"] for action in first] == ["visual_layout_repair_brief_needed"]

    brief.write_text(json.dumps({"source_review_sha256": _file_sha256(review), "actions": [{"code": "table_overflow"}]}), encoding="utf-8")
    second = _page_visual_review_actions(_state(paper=paper, pdf=pdf, review=review, repair_brief=brief))
    assert [action["code"] for action in second] == ["visual_layout_repair_candidate_needed"]

    candidate.write_text(json.dumps({"source_brief_sha256": _file_sha256(brief)}), encoding="utf-8")
    state = _state(paper=paper, pdf=pdf, review=review, repair_brief=brief)
    state.artifacts.latest_visual_repair_candidate_json = str(candidate)
    third = _page_visual_review_actions(state)
    assert [action["code"] for action in third] == ["visual_repair_candidate_review_needed"]
    assert third[0]["automation"] == "human_needed"


def test_page_visual_review_is_stale_when_compiled_pdf_hash_changes(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    pdf = tmp_path / "paper.pdf"
    review = tmp_path / "page-layout-review.json"
    paper.write_text("body", encoding="utf-8")
    pdf.write_bytes(b"new pdf")
    review.write_text(
        json.dumps(
            {
                "manuscript_sha256": _file_sha256(paper),
                "compiled_pdf_sha256": "old-pdf",
                "repair_candidates": [],
            }
        ),
        encoding="utf-8",
    )

    actions = _page_visual_review_actions(_state(paper=paper, pdf=pdf, review=review))

    assert [action["code"] for action in actions] == ["page_layout_review_stale"]


def test_page_visual_actions_distinguish_render_failure_from_missing_review(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    pdf = tmp_path / "paper.pdf"
    review = tmp_path / "page-layout-review.json"
    paper.write_text("body", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    review.write_text(
        json.dumps(
            {
                "manuscript_sha256": _file_sha256(paper),
                "compiled_pdf_sha256": _file_sha256(pdf),
                "render_status": {"status": "fail", "reason": "bad_pdf"},
                "repair_candidates": [],
            }
        ),
        encoding="utf-8",
    )

    actions = _page_visual_review_actions(_state(paper=paper, pdf=pdf, review=review))

    assert [action["code"] for action in actions] == ["page_layout_render_failed"]
    assert "render-evidence blocker" in actions[0]["ralph_instruction"]
