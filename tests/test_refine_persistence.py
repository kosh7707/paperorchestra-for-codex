from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.engine import refine_persistence, refine_stages


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        artifacts=SimpleNamespace(
            paper_full_tex="old-paper.tex",
            latest_review_json="old-review.json",
            latest_validation_json=None,
            compiled_pdf=None,
        ),
        review_history=[SimpleNamespace(overall_score=3.0), SimpleNamespace(overall_score=4.0)],
        notes=[],
        current_phase="refinement",
        active_artifact="old-paper.tex",
        refinement_iteration=1,
    )


def test_refine_stages_facade_reexports_persistence_helpers() -> None:
    assert refine_stages.apply_candidate_only_refinement_state is refine_persistence.apply_candidate_only_refinement_state
    assert refine_stages.apply_accepted_refinement_state is refine_persistence.apply_accepted_refinement_state
    assert refine_stages.apply_rejected_refinement_state is refine_persistence.apply_rejected_refinement_state


def test_apply_candidate_only_refinement_state_restores_prior_review_state() -> None:
    state = _state()

    refine_persistence.apply_candidate_only_refinement_state(
        state,
        temp_state_paper="old-paper.tex",
        temp_latest_review="old-review.json",
        validation_path=Path("validation.json"),
        temp_review_history_len=1,
    )

    assert state.artifacts.paper_full_tex == "old-paper.tex"
    assert state.artifacts.latest_review_json == "old-review.json"
    assert state.artifacts.latest_validation_json == "validation.json"
    assert len(state.review_history) == 1


def test_apply_accepted_refinement_state_sets_artifacts_and_notes() -> None:
    state = _state()

    refine_persistence.apply_accepted_refinement_state(
        state,
        final_path=Path("paper.full.tex"),
        candidate_review_path=Path("review.iter-02.json"),
        candidate_pdf_path=Path("paper.pdf"),
        iteration=2,
        previous_score=4.0,
        candidate_score=4.5,
        compile_preservation=True,
        review_retry_scores=[4.4],
        lane_manifest_path=Path("lane-manifest.refinement.json"),
    )

    assert state.artifacts.paper_full_tex == "paper.full.tex"
    assert state.artifacts.latest_review_json == "review.iter-02.json"
    assert state.artifacts.compiled_pdf == "paper.pdf"
    assert state.current_phase == "complete"
    assert state.active_artifact == "paper.pdf"
    assert state.refinement_iteration == 2
    assert "Accepted refinement iteration 2 (score 4.0 -> 4.5)." in state.notes
    assert "Compile-failed refinement iteration 2 preserved the prior compiled manuscript." in state.notes
    assert "Refinement acceptance used reviewer retry confirmation: 4.4" in state.notes
    assert "Lane manifest recorded: lane-manifest.refinement.json" in state.notes


def test_apply_rejected_refinement_state_restores_previous_artifacts_and_truncates_history() -> None:
    state = _state()

    refine_persistence.apply_rejected_refinement_state(
        state,
        temp_state_paper="old-paper.tex",
        temp_latest_review="old-review.json",
        validation_path=Path("validation.json"),
        temp_review_history_len=1,
        iteration=2,
        previous_score=4.0,
        candidate_score=3.8,
        review_retry_scores=[3.9],
        lane_manifest_path=Path("lane-manifest.refinement.json"),
    )

    assert state.artifacts.paper_full_tex == "old-paper.tex"
    assert state.artifacts.latest_review_json == "old-review.json"
    assert state.artifacts.latest_validation_json == "validation.json"
    assert len(state.review_history) == 1
    assert "Rejected refinement iteration 2 (score 4.0 -> 3.8)." in state.notes
    assert "Refinement rejection persisted after reviewer retry: 3.9" in state.notes
    assert "Lane manifest recorded: lane-manifest.refinement.json" in state.notes
