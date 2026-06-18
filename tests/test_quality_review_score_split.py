from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.session import set_current_session
from paperorchestra.loop_engine.quality import reviews as quality_reviews
from paperorchestra.loop_engine.quality.policy import REQUIRED_REVIEW_AXES
from paperorchestra.loop_engine.quality.review_score_axes import _anti_inflation_violations, _numeric_axis_scores
from paperorchestra.loop_engine.quality.review_score_provenance import _review_provenance_failures
from paperorchestra.loop_engine.quality.review_score_shape import _review_shape_failures
from paperorchestra.loop_engine.quality.utils import _file_sha256


def _valid_axis_scores(score: float = 80.0) -> dict[str, dict[str, object]]:
    return {axis: {"score": score, "justification": f"{axis} has enough evidence."} for axis in REQUIRED_REVIEW_AXES}


def test_review_shape_failures_are_claim_safe_only_and_deduped() -> None:
    malformed = {"schema_version": "legacy", "axis_scores": {"coverage_and_completeness": {"score": 101}}, "summary": {}, "penalties": "none"}

    assert _review_shape_failures(malformed, quality_mode="ralph") == []

    claim_safe_failures = _review_shape_failures(malformed, quality_mode="claim_safe")
    assert claim_safe_failures == [
        "review_axes_incomplete",
        "review_penalties_missing",
        "review_schema_invalid",
        "review_summary_missing",
    ]

    valid = {
        "schema_version": "paper-review/1",
        "axis_scores": _valid_axis_scores(),
        "summary": {"weaknesses": [], "top_improvements": []},
        "penalties": [],
    }
    assert _review_shape_failures(valid, quality_mode="claim_safe") == []


def test_review_provenance_failures_validate_paths_stage_and_hashes(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.json"
    provider = tmp_path / "provider.json"
    manifest = tmp_path / "lane.json"
    for path in (prompt, provider, manifest):
        path.write_text(path.name, encoding="utf-8")

    valid_review = {
        "review_provenance": {
            "schema_version": "review-provenance/1",
            "stage": "review",
            "manuscript_sha256": "m" * 64,
            "reviewer_label": "reviewer-a",
            "provider_name": "codex",
            "provider_command_digest": "digest",
            "prompt_trace_meta_path": str(prompt),
            "provider_identity_path": str(provider),
            "lane_manifest_path": str(manifest),
            "prompt_trace_meta_sha256": _file_sha256(prompt),
            "provider_identity_sha256": _file_sha256(provider),
            "lane_manifest_sha256": _file_sha256(manifest),
        }
    }

    failures, check = _review_provenance_failures(valid_review, current_sha="m" * 64, quality_mode="claim_safe")
    assert failures == []
    assert check["status"] == "pass"
    assert check["reviewer_label"] == "reviewer-a"

    stale = dict(valid_review)
    stale["review_provenance"] = dict(valid_review["review_provenance"], stage="write", manuscript_sha256="0" * 64, prompt_trace_meta_sha256="bad")
    failures, check = _review_provenance_failures(stale, current_sha="m" * 64, quality_mode="claim_safe")
    assert failures == ["review_provenance_stage_mismatch", "review_provenance_stale"]
    assert check["status"] == "fail"


def test_numeric_axis_scores_and_anti_inflation_logic() -> None:
    axes = _numeric_axis_scores(
        {
            "axis_scores": {
                "dict_score": {"score": 45},
                "raw_score": 80,
                "ignored": {"score": "high"},
            }
        }
    )

    assert axes == {"dict_score": 45.0, "raw_score": 80.0}
    assert _anti_inflation_violations(91.0, axes) == [
        "overall_score_above_75_with_sub50_axis",
        "overall_score_above_90_requires_exceptional_evidence",
    ]
    assert _anti_inflation_violations(55.0, {"critical_analysis_and_synthesis": 61.0}) == [
        "critical_analysis_above_60_with_low_overall_score"
    ]


def test_review_section_path_still_resolves_path_objects(tmp_path: Path) -> None:
    set_current_session(tmp_path, "po-section-path")
    review_path = tmp_path / "section_review.json"
    review_path.write_text("{}", encoding="utf-8")
    state = SimpleNamespace(
        artifacts=SimpleNamespace(
            latest_section_review_json=str(review_path),
            paper_full_tex=None,
        )
    )

    assert quality_reviews._section_review_path(tmp_path, state) == review_path
