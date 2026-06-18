from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.feedback.packet_bound_paths import _first_current_bound_existing
from paperorchestra.feedback.packet_artifacts import _artifact_record, _snapshot_operator_packet_artifacts
from paperorchestra.feedback.packet_execution_discovery import _first_existing
from paperorchestra.reviews.citation_integrity_paths import citation_integrity_audit_path, citation_integrity_critic_path


def _operator_packet_artifacts(
    *,
    cwd: str | Path | None,
    state: Any,
    packet_path: Path,
    scope: str,
    paper_path: Path,
    paper_dir: Path,
    pdf_path: str | Path | None,
    manuscript_sha256: str | None,
    qa_plan_path: Path | None,
    qa_execution_path: Path | None,
    operator_execution_path: Path | None,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    required_paper = _artifact_record("paper_full_tex", paper_path, required=True)
    assert required_paper is not None
    artifacts.append(required_paper)
    if scope == "pdf_and_tex":
        pdf_record = _artifact_record("compiled_pdf", pdf_path, required=True)
        assert pdf_record is not None
        artifacts.append(pdf_record)
    for role, artifact_source_path in _optional_packet_artifact_sources(
        cwd=cwd,
        state=state,
        paper_dir=paper_dir,
        manuscript_sha256=manuscript_sha256,
        qa_plan_path=qa_plan_path,
        qa_execution_path=qa_execution_path,
        operator_execution_path=operator_execution_path,
    ):
        record = _artifact_record(role, artifact_source_path)
        if record:
            artifacts.append(record)
    return _snapshot_operator_packet_artifacts(packet_path, artifacts)


def _optional_packet_artifact_sources(
    *,
    cwd: str | Path | None,
    state: Any,
    paper_dir: Path,
    manuscript_sha256: str | None,
    qa_plan_path: Path | None,
    qa_execution_path: Path | None,
    operator_execution_path: Path | None,
) -> list[tuple[str, Any]]:
    return [
        (
            "citation_support_review",
            _first_current_bound_existing(
                "citation_support_review",
                manuscript_sha256,
                paper_dir / "citation_support_review.json",
                artifact_path(cwd, "citation_support_review.json"),
            ),
        ),
        (
            "section_review",
            _first_current_bound_existing(
                "section_review",
                manuscript_sha256,
                state.artifacts.latest_section_review_json,
                paper_dir / "section_review.json",
                artifact_path(cwd, "section_review.json"),
            ),
        ),
        ("quality_eval", _first_current_bound_existing("quality_eval", manuscript_sha256, artifact_path(cwd, "quality-eval.json"))),
        ("citation_integrity_audit", _first_current_bound_existing("citation_integrity_audit", manuscript_sha256, citation_integrity_audit_path(cwd))),
        ("citation_integrity_critic", _first_current_bound_existing("citation_integrity_critic", manuscript_sha256, citation_integrity_critic_path(cwd))),
        ("qa_loop_plan", qa_plan_path),
        ("qa_loop_execution", qa_execution_path),
        ("operator_feedback_execution", operator_execution_path),
        ("source_obligations", _first_existing(state.artifacts.source_obligations_json, artifact_path(cwd, "source_obligations.json"))),
        (
            "figure_placement_review",
            _first_current_bound_existing(
                "figure_placement_review",
                manuscript_sha256,
                state.artifacts.latest_figure_placement_review_json,
                artifact_path(cwd, "figure-placement-review.json"),
                artifact_path(cwd, "figure_placement_review.json"),
            ),
        ),
        ("ralph_brief", _first_existing(artifact_path(cwd, "ralph-brief.md"))),
        ("ralph_handoff", _first_existing(artifact_path(cwd, "ralph-handoff.json"))),
    ]
