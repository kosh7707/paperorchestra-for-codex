from __future__ import annotations

from pathlib import Path

from paperorchestra.engine import refine_results, refine_stages


def test_refine_stages_facade_reexports_result_builders() -> None:
    assert refine_stages.contract_validation_failed_result is refine_results.contract_validation_failed_result
    assert refine_stages.candidate_only_result is refine_results.candidate_only_result
    assert refine_stages.accepted_refinement_result is refine_results.accepted_refinement_result
    assert refine_stages.rejected_refinement_result is refine_results.rejected_refinement_result


def test_contract_validation_failed_result_shape() -> None:
    result = refine_results.contract_validation_failed_result(
        iteration=3,
        score_before=4.25,
        paper_path=Path("paper.full.tex"),
        issues=["unknown citation"],
        validation_path=Path("validation.json"),
        validation_payload={"ok": False},
    )

    assert result == {
        "iteration": 3,
        "accepted": False,
        "score_before": 4.25,
        "score_after": None,
        "paper_path": "paper.full.tex",
        "worklog_path": None,
        "reason": "contract_validation_failed",
        "issues": ["unknown citation"],
        "validation_report_path": "validation.json",
        "validation_report": {"ok": False},
    }


def test_candidate_only_result_merges_contract_preservation_without_mutating_source() -> None:
    preservation = {
        "preserved_prior_after_contract_regression": True,
        "rejected_candidate_path": "rejected.tex",
    }

    result = refine_results.candidate_only_result(
        iteration=2,
        score_before=4.0,
        score_after=4.5,
        axis_scores_before={"clarity": 4.0},
        axis_scores_after={"clarity": 4.5},
        paper_path="paper.full.tex",
        candidate_path=Path("candidate.tex"),
        candidate_sha256="abc123",
        worklog_path=Path("worklog.json"),
        compile_error=None,
        validation_path=Path("validation.json"),
        validation_payload={"warnings": []},
        review_path=Path("review.json"),
        no_op_refinement=False,
        contract_regression_preservation=preservation,
    )

    assert result["candidate_only"] is True
    assert result["accepted"] is False
    assert result["reason"] == "contract_regression_preserved_prior"
    assert result["candidate_path"] == "candidate.tex"
    assert result["review_path"] == "review.json"
    assert result["preserved_prior_after_contract_regression"] is True
    assert preservation == {
        "preserved_prior_after_contract_regression": True,
        "rejected_candidate_path": "rejected.tex",
    }


def test_accepted_refinement_result_names_compile_preservation_and_retries() -> None:
    result = refine_results.accepted_refinement_result(
        iteration=5,
        compile_preservation=True,
        score_before=3.5,
        score_after=3.5,
        paper_path=Path("paper.full.tex"),
        worklog_path=Path("worklog.json"),
        compile_error="latex failed once",
        validation_path=Path("validation.json"),
        validation_payload={"clean": True},
        lane_manifest_path=Path("lane.json"),
        review_retry_paths=["retry.json"],
        review_retry_scores=[3.6],
    )

    assert result["accepted"] is True
    assert result["preservation"] is True
    assert result["reason"] == "compile_failed_preserved_previous"
    assert result["compile_error"] == "latex failed once"
    assert result["review_retry_paths"] == ["retry.json"]
    assert result["review_retry_scores"] == [3.6]


def test_rejected_refinement_result_reason_tracks_compile_failure() -> None:
    compile_failed = refine_results.rejected_refinement_result(
        iteration=1,
        score_before=4.0,
        score_after=4.1,
        paper_path="paper.full.tex",
        worklog_path=Path("worklog.json"),
        compile_error="latex failed",
        validation_path=Path("validation.json"),
        validation_payload={},
        lane_manifest_path=Path("lane.json"),
        review_retry_paths=[],
        review_retry_scores=[],
    )
    score_failed = refine_results.rejected_refinement_result(
        iteration=1,
        score_before=4.0,
        score_after=3.9,
        paper_path="paper.full.tex",
        worklog_path=Path("worklog.json"),
        compile_error=None,
        validation_path=Path("validation.json"),
        validation_payload={},
        lane_manifest_path=Path("lane.json"),
        review_retry_paths=[],
        review_retry_scores=[],
    )

    assert compile_failed["reason"] == "compile_failed"
    assert score_failed["reason"] == "score_regressed_or_tie_break_failed"
