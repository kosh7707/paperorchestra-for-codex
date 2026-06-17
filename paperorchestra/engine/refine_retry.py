from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.engine.refine_review import should_accept_refinement_candidate, should_retry_refinement_review
from paperorchestra.engine.review_stages import _extract_axis_scores, review_current_paper


@dataclass(frozen=True)
class RefinementRetryReviewResult:
    accept: bool
    candidate_review_path: Path
    candidate_score: float
    review_retry_paths: list[str]
    review_retry_scores: list[float]


def maybe_retry_refinement_review(
    *,
    cwd: str | Path | None,
    provider: Any,
    runtime_mode: str,
    candidate_iter: int,
    accept: bool,
    no_op_refinement: bool,
    compile_error: str | None,
    previous_score: float,
    candidate_score: float,
    previous_axes: dict[str, float],
    candidate_review_path: str | Path,
) -> RefinementRetryReviewResult:
    review_retry_paths: list[str] = []
    review_retry_scores: list[float] = []
    if should_retry_refinement_review(
        accept=accept,
        no_op_refinement=no_op_refinement,
        compile_error=compile_error,
        previous_score=previous_score,
        candidate_score=candidate_score,
    ):
        retry_review_path = review_current_paper(
            cwd,
            provider,
            review_name=f"review.iter-{candidate_iter:02d}.retry-01.json",
            runtime_mode=runtime_mode,
        )
        retry_review = read_json(retry_review_path)
        retry_score = float(retry_review.get("overall_score", 0.0))
        retry_axes = _extract_axis_scores(retry_review)
        review_retry_paths.append(str(retry_review_path))
        review_retry_scores.append(retry_score)
        if should_accept_refinement_candidate(
            compile_error=None,
            no_op_refinement=False,
            candidate_score=retry_score,
            previous_score=previous_score,
            candidate_axes=retry_axes,
            previous_axes=previous_axes,
        ):
            candidate_review_path = retry_review_path
            candidate_score = retry_score
            accept = True

    return RefinementRetryReviewResult(
        accept=accept,
        candidate_review_path=Path(candidate_review_path),
        candidate_score=candidate_score,
        review_retry_paths=review_retry_paths,
        review_retry_scores=review_retry_scores,
    )
