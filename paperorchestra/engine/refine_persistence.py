from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.engine.authoring_common import _append_unique_note


def apply_candidate_only_refinement_state(
    state,
    *,
    temp_state_paper: str | None,
    temp_latest_review: str | None,
    validation_path: str | Path,
    temp_review_history_len: int,
) -> Any:
    state.artifacts.paper_full_tex = temp_state_paper
    state.artifacts.latest_review_json = temp_latest_review
    state.artifacts.latest_validation_json = str(validation_path)
    state.review_history = state.review_history[:temp_review_history_len]
    return state


def apply_accepted_refinement_state(
    state,
    *,
    final_path: str | Path,
    candidate_review_path: str | Path,
    candidate_pdf_path: str | Path | None,
    iteration: int,
    previous_score: float,
    candidate_score: float,
    compile_preservation: bool,
    review_retry_scores: list[float],
    lane_manifest_path: str | Path,
) -> Any:
    final_path = Path(final_path)
    state.artifacts.paper_full_tex = str(final_path)
    state.artifacts.latest_review_json = str(candidate_review_path)
    if candidate_pdf_path is not None:
        state.artifacts.compiled_pdf = str(candidate_pdf_path)
        state.current_phase = "complete"
        state.active_artifact = Path(candidate_pdf_path).name
    else:
        state.active_artifact = final_path.name
    state.refinement_iteration = iteration
    state.notes.append(f"Accepted refinement iteration {iteration} (score {previous_score} -> {candidate_score}).")
    if compile_preservation:
        _append_unique_note(
            state,
            f"Compile-failed refinement iteration {iteration} preserved the prior compiled manuscript.",
        )
    if review_retry_scores:
        state.notes.append(
            "Refinement acceptance used reviewer retry confirmation: "
            + ", ".join(str(score) for score in review_retry_scores)
        )
    state.notes.append(f"Lane manifest recorded: {Path(lane_manifest_path).name}")
    return state


def apply_rejected_refinement_state(
    state,
    *,
    temp_state_paper: str | None,
    temp_latest_review: str | None,
    validation_path: str | Path,
    temp_review_history_len: int,
    iteration: int,
    previous_score: float,
    candidate_score: float,
    review_retry_scores: list[float],
    lane_manifest_path: str | Path,
) -> Any:
    state.artifacts.paper_full_tex = temp_state_paper
    state.artifacts.latest_review_json = temp_latest_review
    state.artifacts.latest_validation_json = str(validation_path)
    state.review_history = state.review_history[:temp_review_history_len]
    _append_unique_note(
        state,
        f"Rejected refinement iteration {iteration} (score {previous_score} -> {candidate_score}).",
    )
    if review_retry_scores:
        state.notes.append(
            "Refinement rejection persisted after reviewer retry: "
            + ", ".join(str(score) for score in review_retry_scores)
        )
    state.notes.append(f"Lane manifest recorded: {Path(lane_manifest_path).name}")
    return state
