from __future__ import annotations

from paperorchestra.engine import refine_review


def test_redact_review_scores_for_writer_removes_scorecard_without_mutating_source() -> None:
    payload = {
        "overall_score": 4.0,
        "axis_scores": {"novelty": 3.5},
        "issues": [{"message": "tighten the framing"}],
    }

    redacted = refine_review._redact_review_scores_for_writer(payload)

    assert "overall_score" not in redacted
    assert "axis_scores" not in redacted
    assert redacted["issues"] == payload["issues"]
    assert redacted["score_redaction"]["overall_score_removed"] == "writer_blind_to_reviewer_scores"
    assert payload["overall_score"] == 4.0
    assert payload["axis_scores"] == {"novelty": 3.5}


def test_accept_review_delta_rejects_lower_overall_even_with_axis_tolerance(monkeypatch) -> None:
    monkeypatch.setenv("PAPERO_REFINE_AXIS_TOLERANCE", "1.0")

    assert (
        refine_review._accept_review_delta(
            3.9,
            4.0,
            {"novelty": 10.0},
            {"novelty": 4.0},
        )
        is False
    )


def test_accept_review_delta_uses_non_negative_axis_tolerance(monkeypatch) -> None:
    monkeypatch.setenv("PAPERO_REFINE_AXIS_TOLERANCE", "0.25")

    assert refine_review._accept_review_delta(4.0, 4.0, {"clarity": 3.8}, {"clarity": 4.0}) is True
    assert refine_review._accept_review_delta(4.0, 4.0, {"clarity": 3.7}, {"clarity": 4.0}) is False

    monkeypatch.setenv("PAPERO_REFINE_AXIS_TOLERANCE", "-10")
    assert refine_review._accept_review_delta(4.0, 4.0, {"clarity": 3.8}, {"clarity": 4.0}) is False


def test_accept_review_delta_uses_zero_axis_tolerance_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PAPERO_REFINE_AXIS_TOLERANCE", raising=False)

    assert refine_review._accept_review_delta(4.0, 4.0, {"clarity": 4.0}, {"clarity": 4.0}) is True
    assert refine_review._accept_review_delta(4.0, 4.0, {"clarity": 3.99}, {"clarity": 4.0}) is False


def test_accept_review_delta_ignores_malformed_tolerance(monkeypatch) -> None:
    monkeypatch.setenv("PAPERO_REFINE_AXIS_TOLERANCE", "not-a-float")

    assert refine_review._accept_review_delta(4.0, 4.0, {"clarity": 3.99}, {"clarity": 4.0}) is False
    assert refine_review._accept_review_delta(4.0, 4.0, {}, {"clarity": 4.0}) is True
