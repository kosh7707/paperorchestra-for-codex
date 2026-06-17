from __future__ import annotations

from paperorchestra.core import io
from paperorchestra.engine import latex_postprocess, prompt_context, refine_review, refine_stages


def test_refine_stages_facade_reexports_review_helpers() -> None:
    assert refine_stages._redact_review_scores_for_writer is refine_review._redact_review_scores_for_writer
    assert refine_stages._accept_review_delta is refine_review._accept_review_delta


def test_refine_stages_binds_runtime_dependencies_used_inside_refinement_loop() -> None:
    assert refine_stages.ExtractionError is io.ExtractionError
    assert refine_stages._reviewable_plot_assets_index is latex_postprocess._reviewable_plot_assets_index
    assert refine_stages._reviewable_plot_manifest is latex_postprocess._reviewable_plot_manifest
    assert refine_stages._raise_if_strict_source_citations_unmapped is prompt_context._raise_if_strict_source_citations_unmapped


def test_refine_stages_preserves_legacy_iteration_runtime_reexports() -> None:
    from paperorchestra.engine import completion, reports
    from paperorchestra.manuscript.prompts import PROMPTS

    assert refine_stages._complete_with_runtime_mode is completion._complete_with_runtime_mode
    assert refine_stages._build_completion_request is completion._build_completion_request
    assert refine_stages._provider_name is completion._provider_name
    assert refine_stages._record_validation_report is reports._record_validation_report
    assert refine_stages.collect_paper_contract_issues is reports.collect_paper_contract_issues
    assert refine_stages.PROMPTS is PROMPTS


def test_refine_stages_preserves_legacy_review_helper_reexports() -> None:
    from paperorchestra.engine import review_stages

    assert refine_stages.review_current_paper is review_stages.review_current_paper
    assert refine_stages._extract_axis_scores is review_stages._extract_axis_scores


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
