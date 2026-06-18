from __future__ import annotations

from paperorchestra.reviews import citation_partition, eval_text, evaluation


def test_eval_text_parses_reported_margin_ranges_and_title_matches() -> None:
    assert eval_text.normalize_eval_title("IRIS: A Grounded Review-System!") == "iris a grounded review system"

    margins = eval_text.parse_reported_margin_ranges(
        "The literature review quality improved by 12.5% to 18% in literature review quality. "
        "Overall manuscript quality: 3%-5%."
    )
    assert margins["literature_review_quality"]["min"] == 12.5
    assert margins["literature_review_quality"]["max"] == 18.0
    assert margins["overall_manuscript_quality"]["min"] == 3.0
    assert margins["overall_manuscript_quality"]["max"] == 5.0

    assert eval_text._title_matches_reference("BugLens", "Bug Lens")[0] is True
    assert eval_text._title_matches_reference("A Completely Different Paper", "Bug Lens")[0] is False


def test_partitioned_citation_coverage_matches_priority_partitions_once() -> None:
    coverage = citation_partition.compute_partitioned_citation_coverage(
        [
            {"title": "Sifting the Noise"},
            {"title": "IRIS: A Grounded Review System"},
            {"title": "BugLens"},
        ],
        {"1": "P0", "2": "P1", "3": "P0"},
        ["Sifting-the Noise!", "IRIS Grounded Review System", "Unrelated Paper"],
    )

    assert coverage["partition_coverage"]["P0"]["total"] == 2
    assert coverage["partition_coverage"]["P0"]["matched"] == 1
    assert coverage["partition_coverage"]["P1"]["matched"] == 1
    assert coverage["weighted_priority_recall"] == 0.625
    assert coverage["generated_precision"] == 0.6667
    assert coverage["unmatched_generated_titles"] == ["Unrelated Paper"]


def test_citation_partition_request_formats_numbered_references() -> None:
    request = citation_partition.build_citation_partition_request(
        "Paper body",
        [{"title": "First"}, {"title": ""}, {"title": "Second"}],
    )

    assert request["paper_text"] == "Paper body"
    assert request["reference_count"] == 2
    assert request["references_str"] == "[1] First\n[3] Second"
