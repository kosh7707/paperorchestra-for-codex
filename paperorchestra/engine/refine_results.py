from __future__ import annotations

from os import PathLike
from typing import Any


Pathish = str | PathLike[str]


def _path_str(path: Pathish) -> str:
    return str(path)


def contract_validation_failed_result(
    *,
    iteration: int,
    score_before: float,
    paper_path: Pathish,
    issues: list[str],
    validation_path: Pathish,
    validation_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "accepted": False,
        "score_before": score_before,
        "score_after": None,
        "paper_path": _path_str(paper_path),
        "worklog_path": None,
        "reason": "contract_validation_failed",
        "issues": issues,
        "validation_report_path": _path_str(validation_path),
        "validation_report": validation_payload,
    }


def candidate_only_result(
    *,
    iteration: int,
    score_before: float,
    score_after: float,
    axis_scores_before: dict[str, float],
    axis_scores_after: dict[str, float],
    paper_path: str | None,
    candidate_path: Pathish,
    candidate_sha256: str,
    worklog_path: Pathish,
    compile_error: str | None,
    validation_path: Pathish,
    validation_payload: dict[str, Any],
    review_path: Pathish | None,
    no_op_refinement: bool,
    contract_regression_preservation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "iteration": iteration,
        "accepted": False,
        "candidate_only": True,
        "reason": "candidate_ready_without_generic_acceptance",
        "score_before": score_before,
        "score_after": score_after,
        "axis_scores_before": axis_scores_before,
        "axis_scores_after": axis_scores_after,
        "paper_path": paper_path,
        "candidate_path": _path_str(candidate_path),
        "candidate_sha256": candidate_sha256,
        "worklog_path": _path_str(worklog_path),
        "compile_error": compile_error,
        "validation_report_path": _path_str(validation_path),
        "validation_report": validation_payload,
        "review_path": _path_str(review_path) if review_path else None,
        "no_op_refinement": no_op_refinement,
    }
    if contract_regression_preservation:
        result.update(dict(contract_regression_preservation))
        result["reason"] = "contract_regression_preserved_prior"
    return result


def accepted_refinement_result(
    *,
    iteration: int,
    compile_preservation: bool,
    score_before: float,
    score_after: float,
    paper_path: Pathish,
    worklog_path: Pathish,
    compile_error: str | None,
    validation_path: Pathish,
    validation_payload: dict[str, Any],
    lane_manifest_path: Pathish,
    review_retry_paths: list[str],
    review_retry_scores: list[float],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "accepted": True,
        "preservation": compile_preservation,
        "reason": "compile_failed_preserved_previous" if compile_preservation else "accepted_non_regressive_revision",
        "score_before": score_before,
        "score_after": score_after,
        "paper_path": _path_str(paper_path),
        "worklog_path": _path_str(worklog_path),
        "compile_error": compile_error,
        "validation_report_path": _path_str(validation_path),
        "validation_report": validation_payload,
        "lane_manifest_path": _path_str(lane_manifest_path),
        "review_retry_paths": review_retry_paths,
        "review_retry_scores": review_retry_scores,
    }


def rejected_refinement_result(
    *,
    iteration: int,
    score_before: float,
    score_after: float,
    paper_path: str | None,
    worklog_path: Pathish,
    compile_error: str | None,
    validation_path: Pathish,
    validation_payload: dict[str, Any],
    lane_manifest_path: Pathish,
    review_retry_paths: list[str],
    review_retry_scores: list[float],
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "accepted": False,
        "score_before": score_before,
        "score_after": score_after,
        "paper_path": paper_path,
        "worklog_path": _path_str(worklog_path),
        "reason": "compile_failed" if compile_error else "score_regressed_or_tie_break_failed",
        "compile_error": compile_error,
        "validation_report_path": _path_str(validation_path),
        "validation_report": validation_payload,
        "lane_manifest_path": _path_str(lane_manifest_path),
        "review_retry_paths": review_retry_paths,
        "review_retry_scores": review_retry_scores,
    }
