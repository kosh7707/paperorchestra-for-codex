from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.visual.contact_sheet import write_contact_sheet_indexes
from paperorchestra.visual.page_layout_review import (
    PAGE_LAYOUT_SCHEMA_VERSION,
    VISUAL_REPAIR_BRIEF_SCHEMA_VERSION,
    build_page_layout_review_payload,
    build_visual_repair_brief_payload,
)


def test_contact_sheet_indexes_reference_rendered_page_images(tmp_path: Path) -> None:
    page1 = tmp_path / "page-001.png"
    page2 = tmp_path / "page-002.png"
    page1.write_bytes(b"png1")
    page2.write_bytes(b"png2")

    payload = write_contact_sheet_indexes(
        [
            {"page": 1, "image_path": str(page1)},
            {"page": 2, "image_path": str(page2)},
        ],
        tmp_path,
    )

    assert Path(payload["html"]).exists()
    assert Path(payload["markdown"]).exists()
    html = Path(payload["html"]).read_text(encoding="utf-8")
    markdown = Path(payload["markdown"]).read_text(encoding="utf-8")
    assert "page-001.png" in html
    assert "page-002.png" in html
    assert "![page 1]" in markdown
    assert payload["page_count"] == 2


def test_page_layout_review_marks_visual_review_pending_without_imported_findings(tmp_path: Path) -> None:
    paper = tmp_path / "paper.full.tex"
    paper.write_text("\\section{Method} body", encoding="utf-8")

    payload = build_page_layout_review_payload(
        pdf_path=tmp_path / "paper.pdf",
        manuscript_path=paper,
        rendered_pages=[{"page": 1, "image_path": str(tmp_path / "page-001.png")}],
        contact_sheets={"html": str(tmp_path / "page-contact-sheet.html"), "markdown": str(tmp_path / "page-contact-sheet.md")},
        imported_findings=None,
        render_status={"status": "pass", "backend": "test"},
    )

    assert payload["schema_version"] == PAGE_LAYOUT_SCHEMA_VERSION
    assert payload["status"] == "warn"
    assert payload["warning_codes"] == ["visual_review_pending"]
    assert payload["repair_candidates"][0]["code"] == "visual_review_pending"
    assert payload["repair_candidates"][0]["automation"] == "semi_auto"
    assert payload["requires_visual_reviewer"] is True


def test_imported_visual_findings_become_repair_candidates(tmp_path: Path) -> None:
    findings = {
        "schema_version": "page-visual-findings/1",
        "reviewer": "vision-agent",
        "page_findings": [
            {
                "page": 2,
                "code": "table_overflow",
                "severity": "fail",
                "target": "Table 2",
                "detail": "Right edge exceeds the page boundary.",
                "suggested_fix": "Shorten headers or use a spanning table.",
            }
        ],
        "document_findings": [
            {
                "code": "visual_style_inconsistent",
                "severity": "warn",
                "target": "figures",
                "detail": "Figure colors do not read as one design system.",
                "suggested_fix": "Normalize palette and line weights.",
            },
            {
                "code": "final_artwork_required",
                "severity": "fail",
                "target": "Figure 3",
                "detail": "Generated conceptual art is only a draft placeholder.",
                "suggested_fix": "Replace with human-authored final artwork.",
            },
        ],
    }

    payload = build_page_layout_review_payload(
        pdf_path=tmp_path / "paper.pdf",
        manuscript_path=None,
        rendered_pages=[],
        contact_sheets={},
        imported_findings=findings,
        render_status={"status": "pass", "backend": "test"},
    )

    assert payload["status"] == "fail"
    assert payload["failing_codes"] == ["final_artwork_required", "table_overflow"]
    assert payload["warning_codes"] == ["visual_style_inconsistent"]
    candidates = {item["code"]: item for item in payload["repair_candidates"]}
    assert candidates["table_overflow"]["automation"] == "semi_auto"
    assert candidates["visual_style_inconsistent"]["automation"] == "semi_auto"
    assert candidates["final_artwork_required"]["automation"] == "human_needed"


def test_visual_repair_brief_preserves_claim_location_caption_loop(tmp_path: Path) -> None:
    review = {
        "schema_version": PAGE_LAYOUT_SCHEMA_VERSION,
        "reviewer": "vision-agent",
        "manuscript_sha256": "abc123",
        "repair_candidates": [
            {
                "code": "table_overflow",
                "automation": "semi_auto",
                "target": "Table 2",
                "page": 4,
                "detail": "Right edge exceeds the page boundary.",
                "suggested_fix": "Use smaller columns.",
            }
        ],
    }

    brief = build_visual_repair_brief_payload(review, source_review_path=tmp_path / "page-layout-review.json")

    assert brief["schema_version"] == VISUAL_REPAIR_BRIEF_SCHEMA_VERSION
    assert brief["manuscript_sha256"] == "abc123"
    assert brief["actions"][0]["code"] == "table_overflow"
    assert brief["actions"][0]["automation"] == "semi_auto"
    assert "claim" in " ".join(brief["actions"][0]["acceptance_checks"]).lower()
    assert "caption" in " ".join(brief["actions"][0]["acceptance_checks"]).lower()
    assert brief["actions"][0]["proposed_owner"] == "paperorchestra"


def test_write_page_layout_review_updates_session_artifacts(monkeypatch, tmp_path: Path) -> None:
    from paperorchestra.core.models import InputBundle
    from paperorchestra.core.session import create_session, load_session, save_session
    from paperorchestra.visual import page_layout_review

    materials = tmp_path / "materials"
    materials.mkdir()
    idea = materials / "idea.md"
    experiment = materials / "experiment.md"
    template = materials / "template.tex"
    guide = materials / "guide.md"
    for path in [idea, experiment, template, guide]:
        path.write_text("seed", encoding="utf-8")
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=str(idea),
            experimental_log_path=str(experiment),
            template_path=str(template),
            guidelines_path=str(guide),
        ),
    )
    paper = tmp_path / "paper.full.tex"
    pdf = tmp_path / "paper.pdf"
    paper.write_text("\\section{Method} body", encoding="utf-8")
    pdf.write_bytes(b"pdf")
    state.artifacts.paper_full_tex = str(paper)
    state.artifacts.compiled_pdf = str(pdf)
    save_session(tmp_path, state)

    def fake_render(pdf_path: str | Path, render_dir: str | Path, *, dpi: int = 144):
        rendered = Path(render_dir) / "page-1.png"
        rendered.parent.mkdir(parents=True, exist_ok=True)
        rendered.write_bytes(b"png")
        return {"status": "pass", "backend": "fake", "pages": [{"page": 1, "image_path": str(rendered)}]}

    monkeypatch.setattr(page_layout_review, "render_pdf_pages", fake_render)

    path, payload = page_layout_review.write_page_layout_review(tmp_path)

    refreshed = load_session(tmp_path)
    assert refreshed.artifacts.latest_page_layout_review_json == str(path)
    assert payload["warning_codes"] == ["visual_review_pending"]
    assert Path(payload["contact_sheets"]["html"]).exists()


def test_invalid_imported_findings_do_not_falsely_pass(tmp_path: Path) -> None:
    payload = build_page_layout_review_payload(
        pdf_path=tmp_path / "paper.pdf",
        manuscript_path=None,
        rendered_pages=[],
        contact_sheets={},
        imported_findings={"schema_version": "wrong", "page_findings": []},
        render_status={"status": "pass", "backend": "test"},
    )

    assert payload["status"] == "warn"
    assert payload["imported_findings_valid"] is False
    assert payload["requires_visual_reviewer"] is True
    assert payload["warning_codes"] == ["visual_review_pending"]


def test_valid_empty_imported_findings_can_pass_after_real_reviewer(tmp_path: Path) -> None:
    payload = build_page_layout_review_payload(
        pdf_path=tmp_path / "paper.pdf",
        manuscript_path=None,
        rendered_pages=[],
        contact_sheets={},
        imported_findings={"schema_version": "page-visual-findings/1", "reviewer": "human", "page_findings": [], "document_findings": []},
        render_status={"status": "pass", "backend": "test"},
    )

    assert payload["status"] == "pass"
    assert payload["imported_findings_valid"] is True
    assert payload["requires_visual_reviewer"] is False


def test_render_failure_is_blocking_and_yields_repair_candidate(tmp_path: Path) -> None:
    payload = build_page_layout_review_payload(
        pdf_path=tmp_path / "paper.pdf",
        manuscript_path=None,
        rendered_pages=[],
        contact_sheets={},
        imported_findings={"schema_version": "page-visual-findings/1", "reviewer": "human", "page_findings": [], "document_findings": []},
        render_status={"status": "fail", "reason": "render_failed", "backend": "test"},
    )

    assert payload["status"] == "fail"
    assert payload["failing_codes"] == ["visual_render_failed"]
    assert payload["repair_candidates"][0]["code"] == "visual_render_failed"
    assert payload["repair_candidates"][0]["automation"] == "automatic"


def test_renderer_clears_stale_page_images_on_failed_render(monkeypatch, tmp_path: Path) -> None:
    from paperorchestra.visual import page_render

    stale = tmp_path / "page-1.png"
    stale.write_bytes(b"stale")
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"not a pdf")

    monkeypatch.setattr(page_render.shutil, "which", lambda name: "/bin/false")
    payload = page_render.render_pdf_pages(pdf, tmp_path)

    assert payload["status"] == "fail"
    assert payload["pages"] == []
    assert not stale.exists()
