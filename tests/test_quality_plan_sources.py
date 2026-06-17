from __future__ import annotations

from pathlib import Path

from paperorchestra.loop_engine.quality.plan_sources import build_quality_eval_for_plan


def test_quality_eval_for_plan_marks_matching_citation_review_identity(tmp_path: Path) -> None:
    citation_review = tmp_path / "citation-support.json"
    citation_review.write_text("stable", encoding="utf-8")
    expected_sha = "f379ccb92b9116442dc65bdc35648a85d3786b34779db7f704a901fa07b00cb6"
    quality_eval = {"source_artifacts": {"citation_review_sha256": expected_sha}}

    enriched, identity = build_quality_eval_for_plan(quality_eval, citation_review)

    assert identity.expected_sha256 == expected_sha
    assert identity.current_sha256 == expected_sha
    assert identity.status == "pass"
    assert enriched["source_artifacts"]["citation_review_current_sha256"] == expected_sha
    assert enriched["source_artifacts"]["citation_review_identity_status"] == "pass"
    assert quality_eval == {"source_artifacts": {"citation_review_sha256": expected_sha}}


def test_quality_eval_for_plan_classifies_stale_missing_and_absent_identity(tmp_path: Path) -> None:
    citation_review = tmp_path / "citation-support.json"
    citation_review.write_text("changed", encoding="utf-8")

    _, stale = build_quality_eval_for_plan({"source_artifacts": {"citation_review_sha256": "a" * 64}}, citation_review)
    assert stale.status == "stale_or_divergent"

    missing_current_path = tmp_path / "missing.json"
    enriched_current_only, current_only = build_quality_eval_for_plan(
        {"source_artifacts": {"existing_key": "keep-me"}}, citation_review
    )
    assert current_only.status == "missing_expected_or_current"
    assert enriched_current_only["source_artifacts"]["existing_key"] == "keep-me"

    _, missing_expected_or_current = build_quality_eval_for_plan(
        {"source_artifacts": {"citation_review_sha256": "a" * 64}}, missing_current_path
    )
    assert missing_expected_or_current.status == "missing_expected_or_current"

    _, missing = build_quality_eval_for_plan({"source_artifacts": {}}, missing_current_path)
    assert missing.status == "missing"


def test_quality_eval_for_plan_preserves_truthy_non_string_expected_identity(tmp_path: Path) -> None:
    citation_review = tmp_path / "citation-support.json"
    citation_review.write_text("stable", encoding="utf-8")

    enriched, identity = build_quality_eval_for_plan({"source_artifacts": {"citation_review_sha256": 123}}, citation_review)

    assert identity.expected_sha256 == 123
    assert identity.status == "stale_or_divergent"
    assert enriched["source_artifacts"]["citation_review_sha256"] == 123
