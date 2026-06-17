from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RefinementIterationRun:
    result: dict[str, Any]
    stop_after: bool


@dataclass(frozen=True)
class RefinementValidationOutcome:
    validation_path: Path
    validation_payload: dict[str, Any]
    failure_run: RefinementIterationRun | None


@dataclass(frozen=True)
class PreparedRefinementDraft:
    state: Any
    iteration: Any
    latex: str
    worklog: dict[str, Any]
    lane_type: str
    fallback_used: bool
    lane_notes: list[str]
    runtime_mode: str
    validation_issues: list[Any]
    contract_regression_preservation: Any


@dataclass(frozen=True)
class RefinementCandidateAssessment:
    validation_path: Path
    validation_payload: dict[str, Any]
    candidate_tex_path: Path
    worklog_path: Path
    latex: str
    temp_state_paper: str
    temp_latest_review: str | None
    temp_review_history_len: int
    previous_score: float
    previous_axes: dict[str, float]
    candidate_review_path: str | Path
    candidate_score: float
    candidate_axes: dict[str, float]
    no_op_refinement: bool
    candidate_pdf_path: Path | None
    compile_error: str | None
    compile_preservation: Any
    preserved_compile_error: str | None
    worklog: dict[str, Any]
    lane_notes: list[str]


@dataclass(frozen=True)
class RefinementReviewDecision:
    accept: bool
    candidate_review_path: str | Path
    candidate_score: float
    review_retry_paths: list[str]
    review_retry_scores: list[float]
