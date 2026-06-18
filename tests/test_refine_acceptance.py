from __future__ import annotations

from paperorchestra.engine import refine_review


def test_should_accept_refinement_candidate_handles_compile_and_noop() -> None:
    assert (
        refine_review.should_accept_refinement_candidate(
            compile_error=None,
            no_op_refinement=True,
            candidate_score=1.0,
            previous_score=5.0,
            candidate_axes={},
            previous_axes={},
        )
        is True
    )
    assert (
        refine_review.should_accept_refinement_candidate(
            compile_error="latex failed",
            no_op_refinement=True,
            candidate_score=5.0,
            previous_score=5.0,
            candidate_axes={},
            previous_axes={},
        )
        is False
    )


def test_should_accept_refinement_candidate_uses_review_delta() -> None:
    assert (
        refine_review.should_accept_refinement_candidate(
            compile_error=None,
            no_op_refinement=False,
            candidate_score=4.1,
            previous_score=4.0,
            candidate_axes={"clarity": 4.0},
            previous_axes={"clarity": 4.0},
        )
        is True
    )
    assert (
        refine_review.should_accept_refinement_candidate(
            compile_error=None,
            no_op_refinement=False,
            candidate_score=3.9,
            previous_score=4.0,
            candidate_axes={"clarity": 4.0},
            previous_axes={"clarity": 4.0},
        )
        is False
    )


def test_should_retry_refinement_review_respects_acceptance_compile_and_score_window() -> None:
    assert (
        refine_review.should_retry_refinement_review(
            accept=False,
            no_op_refinement=False,
            compile_error=None,
            previous_score=4.0,
            candidate_score=3.1,
        )
        is True
    )
    assert (
        refine_review.should_retry_refinement_review(
            accept=False,
            no_op_refinement=False,
            compile_error=None,
            previous_score=4.0,
            candidate_score=2.9,
        )
        is False
    )
    assert (
        refine_review.should_retry_refinement_review(
            accept=True,
            no_op_refinement=False,
            compile_error=None,
            previous_score=4.0,
            candidate_score=3.1,
        )
        is False
    )
    assert (
        refine_review.should_retry_refinement_review(
            accept=False,
            no_op_refinement=True,
            compile_error=None,
            previous_score=4.0,
            candidate_score=3.1,
        )
        is False
    )
    assert (
        refine_review.should_retry_refinement_review(
            accept=False,
            no_op_refinement=False,
            compile_error="latex failed",
            previous_score=4.0,
            candidate_score=3.1,
        )
        is False
    )


def test_should_retry_refinement_review_includes_exact_one_point_drop_boundary() -> None:
    assert (
        refine_review.should_retry_refinement_review(
            accept=False,
            no_op_refinement=False,
            compile_error=None,
            previous_score=4.0,
            candidate_score=3.0,
        )
        is True
    )
