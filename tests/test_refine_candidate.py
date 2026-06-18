from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.engine import refine_candidate


def test_snapshot_refinement_state_uses_review_history_when_present() -> None:
    state = SimpleNamespace(
        artifacts=SimpleNamespace(paper_full_tex="paper.tex", latest_review_json="review.latest.json"),
        review_history=[SimpleNamespace(overall_score=4.5, axes={"clarity": 4.2})],
    )

    snapshot = refine_candidate.snapshot_refinement_state(
        state,
        review_payload={"overall_score": 3.1, "axis_scores": {"clarity": 3.0}},
    )

    assert snapshot.temp_state_paper == "paper.tex"
    assert snapshot.temp_latest_review == "review.latest.json"
    assert snapshot.temp_review_history_len == 1
    assert snapshot.previous_score == 4.5
    assert snapshot.previous_axes == {"clarity": 4.2}


def test_snapshot_refinement_state_falls_back_to_review_payload_without_history() -> None:
    state = SimpleNamespace(
        artifacts=SimpleNamespace(paper_full_tex="paper.tex", latest_review_json="review.latest.json"),
        review_history=[],
    )

    snapshot = refine_candidate.snapshot_refinement_state(
        state,
        review_payload={"overall_score": 3.1, "axis_scores": {"clarity": 3.0}},
    )

    assert snapshot.previous_score == 3.1
    assert snapshot.previous_axes == {"clarity": 3.0}


def test_review_refinement_candidate_reuses_prior_review_for_no_op(monkeypatch) -> None:
    def fail_review(*_args, **_kwargs):
        raise AssertionError("review_current_paper should not run for no-op refinement")

    monkeypatch.setattr(refine_candidate, "review_current_paper", fail_review)
    state = SimpleNamespace(artifacts=SimpleNamespace(latest_review_json="state-review.json"))
    iteration = SimpleNamespace(current_paper="same", review_payload={"overall_score": 4.0})
    snapshot = refine_candidate.RefinementStateSnapshot(
        temp_state_paper="paper.tex",
        temp_latest_review="snapshot-review.json",
        temp_review_history_len=2,
        previous_score=4.0,
        previous_axes={"clarity": 4.0},
    )

    review = refine_candidate.review_refinement_candidate(
        cwd=None,
        provider=object(),
        state=state,
        iteration=iteration,
        candidate_tex_path=Path("candidate.tex"),
        latex="same",
        runtime_mode="compatibility",
        snapshot=snapshot,
    )

    assert review.no_op_refinement is True
    assert review.candidate_review_path == Path("snapshot-review.json")
    assert review.candidate_score == 4.0
    assert review.candidate_axes == {"clarity": 4.0}


def test_review_refinement_candidate_reviews_changed_candidate(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    def fake_save_session(cwd, state):
        calls.append(("save", state.artifacts.paper_full_tex))

    def fake_review_current_paper(cwd, provider, *, review_name: str, runtime_mode: str):
        calls.append(("review", review_name))
        assert runtime_mode == "compatibility"
        return Path("review.iter-03.json")

    monkeypatch.setattr(refine_candidate, "save_session", fake_save_session)
    monkeypatch.setattr(refine_candidate, "review_current_paper", fake_review_current_paper)
    monkeypatch.setattr(refine_candidate, "read_json", lambda path: {"overall_score": 4.7, "axis_scores": {"clarity": 4.6}})
    state = SimpleNamespace(artifacts=SimpleNamespace(paper_full_tex="paper.tex", latest_review_json="state-review.json"))
    iteration = SimpleNamespace(candidate_iter=3, current_paper="before", review_payload={"overall_score": 4.0})
    snapshot = refine_candidate.RefinementStateSnapshot(
        temp_state_paper="paper.tex",
        temp_latest_review="snapshot-review.json",
        temp_review_history_len=2,
        previous_score=4.0,
        previous_axes={"clarity": 4.0},
    )

    review = refine_candidate.review_refinement_candidate(
        cwd=None,
        provider=object(),
        state=state,
        iteration=iteration,
        candidate_tex_path=Path("candidate.tex"),
        latex="after",
        runtime_mode="compatibility",
        snapshot=snapshot,
    )

    assert calls == [("save", "candidate.tex"), ("review", "review.iter-03.json")]
    assert review.no_op_refinement is False
    assert review.candidate_review_path == Path("review.iter-03.json")
    assert review.candidate_score == 4.7
    assert review.candidate_axes == {"clarity": 4.6}
