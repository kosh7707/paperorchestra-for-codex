from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from paperorchestra.fresh_smoke import normalize_operator_feedback_draft
from paperorchestra.fidelity import _strict_content_gate_issues
from paperorchestra.models import InputBundle
from paperorchestra.narrative import write_planning_artifacts
from paperorchestra.operator_feedback import (
    _figure_issue_context,
    _operator_refinement_constraints,
    build_operator_review_packet,
)
from paperorchestra.pipeline import write_figure_placement_review
from paperorchestra.quality_loop import _figure_grounding_check, build_quality_eval
from paperorchestra.session import artifact_path, create_session, load_session, save_session


def _packet() -> dict[str, object]:
    return {
        "packet_sha256": "packet-sha",
        "manuscript_sha256": "manuscript-sha",
        "artifacts": [],
    }


def _issue(index: int, *, severity: str = "minor", role: str = "qa_loop_plan") -> dict[str, str]:
    return {
        "source_artifact_role": role,
        "source_item_key": f"item-{index}",
        "target_section": "Whole manuscript",
        "severity": severity,
        "rationale": f"Issue {index} rationale.",
        "suggested_action": f"Issue {index} action.",
        "authority_class": "author_feedback",
        "owner_category": "author",
    }


def test_normalized_operator_feedback_caps_generated_candidate_issues_to_atomic_targets() -> None:
    draft = {
        "intent": "generate_new_operator_candidate",
        "issues": [
            _issue(1, severity="minor"),
            _issue(2, severity="blocker", role="citation_support_review"),
            _issue(3, severity="major", role="figure_placement_review"),
            _issue(4, severity="major", role="quality_eval"),
            _issue(5, severity="minor"),
        ],
    }

    normalized = normalize_operator_feedback_draft(_packet(), draft)

    assert normalized["intent"] == "generate_new_operator_candidate"
    assert len(normalized["issues"]) == 3
    assert [issue["source_item_key"] for issue in normalized["issues"]] == ["item-2", "item-3", "item-4"]


def test_normalized_operator_feedback_prioritizes_compiled_pdf_layout_issues() -> None:
    draft = {
        "intent": "generate_new_operator_candidate",
        "issues": [
            _issue(1, severity="minor"),
            _issue(2, severity="major", role="quality_eval"),
            _issue(3, severity="major", role="compiled_pdf"),
            _issue(4, severity="major", role="qa_loop_plan"),
            _issue(5, severity="minor", role="figure_placement_review"),
        ],
    }

    normalized = normalize_operator_feedback_draft(_packet(), draft)

    assert any(issue["source_artifact_role"] == "compiled_pdf" for issue in normalized["issues"])


def test_operator_feedback_accepts_generic_evidence_and_layout_owner_categories() -> None:
    packet = _packet()
    evidence_issue = _issue(1, role="section_review")
    evidence_issue["owner_category"] = "evidence"
    evidence_issue["authority_class"] = "evidence_alignment"
    layout_issue = _issue(2, role="compiled_pdf")
    layout_issue["owner_category"] = "layout"
    layout_issue["authority_class"] = "layout_quality"
    draft = {"intent": "generate_new_operator_candidate", "issues": [evidence_issue, layout_issue]}

    normalized = normalize_operator_feedback_draft(packet, draft)

    assert [issue["owner_category"] for issue in normalized["issues"]] == ["evidence", "layout"]


def test_normalized_operator_feedback_preserves_rendered_pdf_no_issues_attestation() -> None:
    attestation = {
        "compiled_pdf_sha256": "a" * 64,
        "rendered_pdf_manifest_sha256": "b" * 64,
        "reviewed_page_count": 3,
        "statement": "Reviewed all rendered PDF pages and found no layout-only issues.",
    }

    normalized = normalize_operator_feedback_draft(
        _packet(),
        {"intent": "generate_new_operator_candidate", "issues": [_issue(1)], "rendered_pdf_no_issues": attestation},
    )

    assert normalized["rendered_pdf_no_issues"] == attestation


def test_operator_refinement_constraints_do_not_treat_dense_citations_as_forbidden_new_failure() -> None:
    constraints = _operator_refinement_constraints(
        {"tiers": {"tier_2_claim_safety": {"failing_codes": ["citation_bomb_detected"]}}},
        {"failing_codes": ["citation_bomb_detected"]},
    )

    assert "citation_bomb_detected" not in constraints["forbidden_new_tier2_codes"]
    assert all("citation-bomb" not in item.lower() for item in constraints["hard_constraints"])


def test_figure_issue_context_exposes_atomic_caption_and_asset_failures() -> None:
    payload = {
        "schema_version": "figure-placement-review/1",
        "status": "fail",
        "figures": [
            {
                "label": "fig:portrait",
                "section_title": "Background",
                "caption": "Portrait-style supplied visual asset included without using it as evidence.",
                "failing_codes": ["nontechnical_visual_asset_in_body", "figure_caption_process_or_placeholder"],
                "warning_codes": ["figure_unreferenced"],
            }
        ],
    }

    context = _figure_issue_context(payload)

    assert context[0]["label"] == "fig:portrait"
    assert context[0]["section_title"] == "Background"
    assert context[0]["failing_codes"] == ["nontechnical_visual_asset_in_body", "figure_caption_process_or_placeholder"]
    assert "Remove or quarantine" in context[0]["suggested_fix"]


def test_figure_issue_context_exposes_asset_reference_and_manifest_context() -> None:
    payload = {
        "schema_version": "figure-placement-review/1",
        "status": "fail",
        "figures": [
            {
                "label": "fig:latency",
                "section_title": "Results",
                "caption": "Author biography profile photograph.",
                "included_assets": ["fig_latency_breakdown.tex"],
                "nearby_reference_context": "Figure~\\cref{fig:latency} compares latency across workloads.",
                "plot_manifest_match": {
                    "figure_id": "fig:latency",
                    "title": "Latency breakdown",
                    "purpose": "Compare request latency across workload stages.",
                },
                "failing_codes": ["figure_caption_plot_purpose_mismatch"],
                "warning_codes": [],
            }
        ],
    }

    context = _figure_issue_context(payload)

    assert context[0]["included_assets"] == ["fig_latency_breakdown.tex"]
    assert "compares latency" in context[0]["nearby_reference_context"]
    assert context[0]["plot_manifest_match"]["purpose"] == "Compare request latency across workload stages."


def _init_packet_session(root: Path, latex: str):
    for name, content in {
        "idea.md": "# Idea\n",
        "experimental_log.md": "# Log\n",
        "template.tex": "\\documentclass{article}\n\\begin{document}\\end{document}\n",
        "guidelines.md": "Guidelines\n",
    }.items():
        (root / name).write_text(content, encoding="utf-8")
    (root / "figures").mkdir()
    state = create_session(
        root,
        InputBundle(
            idea_path=str(root / "idea.md"),
            experimental_log_path=str(root / "experimental_log.md"),
            template_path=str(root / "template.tex"),
            guidelines_path=str(root / "guidelines.md"),
            figures_dir=str(root / "figures"),
            cutoff_date="2024-11-01",
        ),
    )
    paper = artifact_path(root, "paper.full.tex")
    paper.write_text(latex, encoding="utf-8")
    state.artifacts.paper_full_tex = str(paper)
    save_session(root, state)
    manuscript_hash = hashlib.sha256(paper.read_bytes()).hexdigest()
    artifact_path(root, "qa-loop.plan.json").write_text(
        json.dumps(
            {
                "schema_version": "qa-loop-plan/1",
                "session_id": state.session_id,
                "verdict": "human_needed",
                "quality_eval_summary": {"manuscript_hash": f"sha256:{manuscript_hash}"},
            }
        ),
        encoding="utf-8",
    )
    return state


def test_operator_review_packet_includes_current_bound_figure_placement_review() -> None:
    latex = (
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Results}\n"
        "Figure~\\ref{fig:architecture} summarizes the method.\n"
        "\\begin{figure}[t]\n"
        "\\includegraphics[width=0.9\\linewidth]{architecture_overview.pdf}\n"
        "\\caption{Architecture overview of the system components.}\n"
        "\\label{fig:architecture}\n"
        "\\end{figure}\n"
        "\\end{document}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _init_packet_session(root, latex)
        figure_path, figure_payload = write_figure_placement_review(root)

        _packet_path, packet = build_operator_review_packet(root)

        figure_records = [artifact for artifact in packet["artifacts"] if artifact["role"] == "figure_placement_review"]
        assert len(figure_records) == 1
        assert figure_records[0]["sha256"] == hashlib.sha256(figure_path.read_bytes()).hexdigest()
        frozen_payload = json.loads(Path(figure_records[0]["path"]).read_text(encoding="utf-8"))
        assert frozen_payload["manuscript_sha256"] == figure_payload["manuscript_sha256"]


def test_strict_content_gate_surfaces_figure_failures() -> None:
    latex = "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_packet_session(root, latex)
        paper = Path(state.artifacts.paper_full_tex)
        figure_path = artifact_path(root, "figure-placement-review.json")
        figure_path.write_text(
            json.dumps(
                {
                    "schema_version": "figure-placement-review/1",
                    "status": "fail",
                    "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "failures": [
                        {
                            "code": "figure_caption_process_or_placeholder",
                            "message": "fig:bad: Caption contains process text.",
                        }
                    ],
                    "warnings": [],
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.latest_figure_placement_review_json = str(figure_path)
        save_session(root, state)

        issues = _strict_content_gate_issues(load_session(root), artifact_path(root, "x").parent)

    figure_issues = [issue for issue in issues if issue.get("kind") == "figure_placement_failure"]
    assert figure_issues
    assert figure_issues[0]["code"] == "figure_caption_process_or_placeholder"
    assert figure_issues[0]["severity"] == "error"


def test_operator_review_packet_omits_unbound_or_stale_figure_placement_review() -> None:
    latex = "\\documentclass{article}\n\\begin{document}\nBody.\n\\end{document}\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_packet_session(root, latex)
        current_hash = hashlib.sha256(Path(state.artifacts.paper_full_tex).read_bytes()).hexdigest()
        figure_path = artifact_path(root, "figure-placement-review.json")
        figure_path.write_text(
            json.dumps({"schema_version": "figure-placement-review/1", "status": "pass", "failing_codes": []}),
            encoding="utf-8",
        )

        _packet_path, packet = build_operator_review_packet(root)
        assert "figure_placement_review" not in {artifact["role"] for artifact in packet["artifacts"]}

        figure_path.write_text(
            json.dumps(
                {
                    "schema_version": "figure-placement-review/1",
                    "status": "pass",
                    "manuscript_sha256": "0" * len(current_hash),
                    "failing_codes": [],
                }
            ),
            encoding="utf-8",
        )

        _packet_path, packet = build_operator_review_packet(root)
        assert "figure_placement_review" not in {artifact["role"] for artifact in packet["artifacts"]}


def test_figure_grounding_check_fails_unsafe_figures_and_warns_only_for_unreferenced_technical_figures() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        unsafe = root / "unsafe.json"
        unsafe.write_text(
            json.dumps(
                {
                    "schema_version": "figure-placement-review/1",
                    "status": "fail",
                    "failing_codes": ["nontechnical_visual_asset_in_body"],
                    "warning_codes": ["figure_unreferenced"],
                }
            ),
            encoding="utf-8",
        )
        warning = root / "warning.json"
        warning.write_text(
            json.dumps(
                {
                    "schema_version": "figure-placement-review/1",
                    "status": "warn",
                    "failing_codes": [],
                    "warning_codes": ["figure_unreferenced"],
                }
            ),
            encoding="utf-8",
        )

        assert _figure_grounding_check(SimpleNamespace(artifacts=SimpleNamespace(latest_figure_placement_review_json=str(unsafe))))[
            "status"
        ] == "fail"
        warning_check = _figure_grounding_check(
            SimpleNamespace(artifacts=SimpleNamespace(latest_figure_placement_review_json=str(warning)))
        )
        assert warning_check["status"] == "warn"
        assert warning_check["failing_codes"] == []


def test_claim_safe_quality_eval_fails_stale_clean_figure_placement_review() -> None:
    latex = (
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Results}\n"
        "Figure~\\ref{fig:architecture} summarizes the method.\n"
        "\\begin{figure}[t]\n"
        "\\includegraphics[width=0.9\\linewidth]{architecture_overview.pdf}\n"
        "\\caption{Architecture overview of the system components.}\n"
        "\\label{fig:architecture}\n"
        "\\end{figure}\n"
        "\\end{document}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = _init_packet_session(root, latex)
        write_planning_artifacts(root)
        state = load_session(root)
        pdf = root / "paper.full.pdf"
        pdf.write_bytes(b"%PDF-1.5\n")
        paper = Path(state.artifacts.paper_full_tex)
        compile_report = artifact_path(root, "compile-report.json")
        compile_report.write_text(
            json.dumps(
                {
                    "clean": True,
                    "manuscript_sha256": hashlib.sha256(paper.read_bytes()).hexdigest(),
                    "pdf_path": str(pdf),
                    "pdf_exists": True,
                    "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        stale_figure = artifact_path(root, "figure-placement-review.json")
        stale_figure.write_text(
            json.dumps(
                {
                    "schema_version": "figure-placement-review/1",
                    "status": "pass",
                    "manuscript_sha256": "0" * 64,
                    "failing_codes": [],
                    "warning_codes": [],
                }
            ),
            encoding="utf-8",
        )
        state.artifacts.latest_compile_report_json = str(compile_report)
        state.artifacts.compiled_pdf = str(pdf)
        state.artifacts.latest_figure_placement_review_json = str(stale_figure)
        save_session(root, state)

        reproducibility = {"citation_artifact_issues": [], "strict_content_gate_issues": [], "prompt_trace_file_count": 1, "verdict": "PASS"}
        with patch("paperorchestra.quality_loop._manuscript_prompt_leakage", return_value=[]):
            payload = build_quality_eval(root, quality_mode="claim_safe", reproducibility=reproducibility, fidelity={})

        figure_grounding = payload["tiers"]["tier_2_claim_safety"]["checks"]["figure_grounding"]
        assert figure_grounding["status"] == "fail"
        assert "figure_placement_review_stale" in payload["tiers"]["tier_2_claim_safety"]["failing_codes"]
