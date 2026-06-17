from __future__ import annotations

from pathlib import Path

from paperorchestra.engine import refine_retry, refine_stages


def test_refine_stages_facade_reexports_retry_review_helpers() -> None:
    assert refine_stages.RefinementRetryReviewResult is refine_retry.RefinementRetryReviewResult
    assert refine_stages.maybe_retry_refinement_review is refine_retry.maybe_retry_refinement_review


def test_retry_review_skips_when_policy_declines(monkeypatch) -> None:
    def fail_review(*_args, **_kwargs):
        raise AssertionError("review_current_paper should not run when retry policy declines")

    monkeypatch.setattr(refine_retry, "review_current_paper", fail_review)
    result = refine_retry.maybe_retry_refinement_review(
        cwd=None,
        provider=object(),
        runtime_mode="compatibility",
        candidate_iter=4,
        accept=True,
        no_op_refinement=False,
        compile_error=None,
        previous_score=4.0,
        candidate_score=3.8,
        previous_axes={"clarity": 4.0},
        candidate_review_path=Path("review.iter-04.json"),
    )

    assert result.accept is True
    assert result.review_retry_paths == []
    assert result.review_retry_scores == []
    assert result.candidate_review_path == Path("review.iter-04.json")
    assert result.candidate_score == 3.8


def test_retry_review_records_retry_without_adopting_rejected_retry(monkeypatch) -> None:
    monkeypatch.setattr(
        refine_retry,
        "review_current_paper",
        lambda cwd, provider, *, review_name, runtime_mode: Path("review.iter-04.retry-01.json"),
    )
    monkeypatch.setattr(
        refine_retry,
        "read_json",
        lambda path: {"overall_score": 3.5, "axis_scores": {"clarity": 3.5}},
    )
    result = refine_retry.maybe_retry_refinement_review(
        cwd=None,
        provider=object(),
        runtime_mode="compatibility",
        candidate_iter=4,
        accept=False,
        no_op_refinement=False,
        compile_error=None,
        previous_score=4.0,
        candidate_score=3.2,
        previous_axes={"clarity": 4.0},
        candidate_review_path=Path("review.iter-04.json"),
    )

    assert result.accept is False
    assert result.review_retry_paths == ["review.iter-04.retry-01.json"]
    assert result.review_retry_scores == [3.5]
    assert result.candidate_review_path == Path("review.iter-04.json")
    assert result.candidate_score == 3.2


def test_retry_review_adopts_accepted_retry(monkeypatch) -> None:
    retry_payload = {"overall_score": 4.2, "axis_scores": {"clarity": 4.2}}
    monkeypatch.setattr(
        refine_retry,
        "review_current_paper",
        lambda cwd, provider, *, review_name, runtime_mode: Path("review.iter-04.retry-01.json"),
    )
    monkeypatch.setattr(refine_retry, "read_json", lambda path: retry_payload)
    result = refine_retry.maybe_retry_refinement_review(
        cwd=None,
        provider=object(),
        runtime_mode="compatibility",
        candidate_iter=4,
        accept=False,
        no_op_refinement=False,
        compile_error=None,
        previous_score=4.0,
        candidate_score=3.2,
        previous_axes={"clarity": 4.0},
        candidate_review_path=Path("review.iter-04.json"),
    )

    assert result.accept is True
    assert result.review_retry_paths == ["review.iter-04.retry-01.json"]
    assert result.review_retry_scores == [4.2]
    assert result.candidate_review_path == Path("review.iter-04.retry-01.json")
    assert result.candidate_score == 4.2
