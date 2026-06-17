from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import save_session
from paperorchestra.engine.review_stages import _extract_axis_scores, review_current_paper


@dataclass(frozen=True)
class RefinementStateSnapshot:
    temp_state_paper: str | None
    temp_latest_review: str | None
    temp_review_history_len: int
    previous_score: float
    previous_axes: dict[str, float]


@dataclass(frozen=True)
class RefinementCandidateReview:
    candidate_review_path: Path
    candidate_score: float
    candidate_axes: dict[str, float]
    no_op_refinement: bool


def snapshot_refinement_state(state: Any, *, review_payload: dict[str, Any]) -> RefinementStateSnapshot:
    previous_snapshot = state.review_history[-1] if state.review_history else None
    return RefinementStateSnapshot(
        temp_state_paper=state.artifacts.paper_full_tex,
        temp_latest_review=state.artifacts.latest_review_json,
        temp_review_history_len=len(state.review_history),
        previous_score=previous_snapshot.overall_score if previous_snapshot else float(review_payload.get("overall_score", 0.0)),
        previous_axes=previous_snapshot.axes if previous_snapshot else _extract_axis_scores(review_payload),
    )


def review_refinement_candidate(
    *,
    cwd: str | Path | None,
    provider: Any,
    state: Any,
    iteration: Any,
    candidate_tex_path: str | Path,
    latex: str,
    runtime_mode: str,
    snapshot: RefinementStateSnapshot,
) -> RefinementCandidateReview:
    no_op_refinement = latex == iteration.current_paper
    if no_op_refinement:
        return RefinementCandidateReview(
            candidate_review_path=Path(snapshot.temp_latest_review or state.artifacts.latest_review_json or ""),
            candidate_score=snapshot.previous_score,
            candidate_axes=snapshot.previous_axes,
            no_op_refinement=True,
        )

    state.artifacts.paper_full_tex = str(candidate_tex_path)
    save_session(cwd, state)
    candidate_review_path = review_current_paper(
        cwd,
        provider,
        review_name=f"review.iter-{iteration.candidate_iter:02d}.json",
        runtime_mode=runtime_mode,
    )
    candidate_review = read_json(candidate_review_path)
    return RefinementCandidateReview(
        candidate_review_path=Path(candidate_review_path),
        candidate_score=float(candidate_review.get("overall_score", 0.0)),
        candidate_axes=_extract_axis_scores(candidate_review),
        no_op_refinement=False,
    )
