from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from paperorchestra.core.session import artifact_path, runtime_root, set_current_session
from paperorchestra.loop_engine.quality import artifact_checks
from paperorchestra.loop_engine.quality import eval as quality_eval
from paperorchestra.loop_engine.quality.policy import HISTORY_FILENAME
from paperorchestra.loop_engine.ralph.state import QA_LOOP_HANDOFF_FILENAME


def test_quality_eval_facade_exports_artifact_checks() -> None:
    assert quality_eval._ralph_evidence_check is artifact_checks._ralph_evidence_check
    assert quality_eval._figure_grounding_check is artifact_checks._figure_grounding_check


def test_ralph_evidence_check_is_strict_only_in_claim_safe(tmp_path: Path) -> None:
    set_current_session(tmp_path, "po-test")

    assert artifact_checks._ralph_evidence_check(tmp_path, quality_mode="ralph")["status"] == "pass"

    claim_safe = artifact_checks._ralph_evidence_check(tmp_path, quality_mode="claim_safe")
    assert claim_safe["status"] == "fail"
    assert claim_safe["failing_codes"] == ["qa_loop_history_missing", "ralph_handoff_missing"]

    handoff_path = artifact_path(tmp_path, QA_LOOP_HANDOFF_FILENAME)
    handoff_path.write_text(
        json.dumps(
            {
                "execution_contract": {
                    "ralph_required": True,
                    "critic_required": True,
                    "citation_integrity_gate_required": True,
                }
            }
        ),
        encoding="utf-8",
    )
    history_path = runtime_root(tmp_path) / HISTORY_FILENAME
    history_path.write_text("[]", encoding="utf-8")

    passed = artifact_checks._ralph_evidence_check(tmp_path, quality_mode="claim_safe")
    assert passed["status"] == "pass"
    assert passed["failing_codes"] == []
    assert passed["ralph_handoff_sha256"]
    assert passed["qa_loop_history_sha256"]


def test_figure_grounding_check_reports_missing_unbound_stale_and_issue_figures(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("paper", encoding="utf-8")
    review = tmp_path / "figure-review.json"
    state = SimpleNamespace(
        artifacts=SimpleNamespace(
            paper_full_tex=str(paper),
            latest_figure_placement_review_json=str(review),
        )
    )

    assert artifact_checks._figure_grounding_check(state)["status"] == "skipped"

    review.write_text('{"status":"pass"}', encoding="utf-8")
    unbound = artifact_checks._figure_grounding_check(state)
    assert unbound["status"] == "fail"
    assert unbound["failing_codes"] == ["figure_placement_review_unbound"]

    review.write_text(json.dumps({"status": "pass", "manuscript_sha256": "0" * 64}), encoding="utf-8")
    stale = artifact_checks._figure_grounding_check(state)
    assert stale["status"] == "fail"
    assert stale["failing_codes"] == ["figure_placement_review_stale"]

    expected_sha = quality_eval._file_sha256(paper)
    review.write_text(
        json.dumps(
            {
                "status": "warn",
                "paper_full_tex_sha256": f"sha256:{expected_sha}",
                "warning_codes": ["figure_caption_weak"],
                "figures": [
                    {
                        "label": "fig:one",
                        "section_title": "Method",
                        "warning_codes": ["figure_caption_weak"],
                        "included_assets": ["plot.pdf"],
                        "nearby_reference_context": "x" * 700,
                        "plot_manifest_match": {"status": "pass"},
                    },
                    {"label": "fig:clean"},
                ],
            }
        ),
        encoding="utf-8",
    )
    warned = artifact_checks._figure_grounding_check(state)
    assert warned["status"] == "warn"
    assert warned["warning_codes"] == ["figure_caption_weak"]
    assert warned["figures"] == [
        {
            "label": "fig:one",
            "section_title": "Method",
            "failing_codes": [],
            "warning_codes": ["figure_caption_weak"],
            "included_assets": ["plot.pdf"],
            "nearby_reference_context": "x" * 500,
            "plot_manifest_match": {"status": "pass"},
        }
    ]
