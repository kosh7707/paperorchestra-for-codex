from __future__ import annotations

from paperorchestra.reviews import generated_citations, review_gate_comparison


def test_review_gate_comparison_payload_detects_missing_shape_and_anti_inflation() -> None:
    latest_review = {
        "overall_score": 91,
        "axis_scores": {
            "coverage_and_completeness": {"score": 45},
            "critical_analysis_and_synthesis": {"score": 70},
            "unexpected_axis": {"score": 80},
        },
        "citation_statistics": {"estimated_unique_citations": 7},
        "summary": {"strengths": []},
        "questions": [],
        "penalties": [],
    }

    payload = review_gate_comparison.build_review_gate_payload(
        session_id="s1",
        review_path="review.json",
        latest_review=latest_review,
    )

    assert payload["present_axes"] == [
        "coverage_and_completeness",
        "critical_analysis_and_synthesis",
        "unexpected_axis",
    ]
    assert "relevance_and_focus" in payload["missing_axes"]
    assert payload["extra_axes"] == ["unexpected_axis"]
    assert payload["anti_inflation_violations"] == [
        "overall_score_above_75_with_sub50_axis",
        "overall_score_above_90_requires_exceptional_evidence",
    ]
    assert payload["comparability_status"] == "partial"


def test_review_gate_payload_preserves_malformed_truthy_review_as_partial() -> None:
    payload = review_gate_comparison.build_review_gate_payload(
        session_id="s1",
        review_path="review.json",
        latest_review=["malformed but present"],
    )

    assert payload["comparability_status"] == "partial"
    assert payload["has_citation_statistics"] is False
    assert payload["has_summary"] is False
    assert payload["has_questions"] is False
    assert payload["missing_citation_statistics_keys"] == review_gate_comparison.EXPECTED_CITATION_STATISTICS_KEYS
    assert payload["missing_summary_keys"] == review_gate_comparison.EXPECTED_REVIEW_SUMMARY_KEYS


def test_generated_citation_titles_extracts_and_deduplicates_resolved_titles() -> None:
    latex = r"First \cite{foo, bar}. Repeated \citep[see]{foo}. Missing \cite{baz}."
    citation_map = {
        "foo": {"title": "IRIS: A Grounded Review System", "paper_id": "p1"},
        "bar": {"title": "IRIS - A Grounded Review System", "paper_id": "p2"},
        "baz": {"title": "BugLens", "paper_id": "p3"},
    }

    payload = generated_citations.build_generated_citation_titles_payload(
        session_id="s1",
        latex_text=latex,
        citation_map=citation_map,
    )

    assert payload["cited_keys"] == ["foo", "bar", "baz"]
    assert payload["generated_titles"] == ["IRIS: A Grounded Review System", "BugLens"]
    assert payload["resolved_entries"] == [
        {
            "citation_key": "foo",
            "title": "IRIS: A Grounded Review System",
            "normalized_title": "iris a grounded review system",
            "paper_id": "p1",
        },
        {
            "citation_key": "baz",
            "title": "BugLens",
            "normalized_title": "buglens",
            "paper_id": "p3",
        },
    ]
    assert payload["count"] == 2
