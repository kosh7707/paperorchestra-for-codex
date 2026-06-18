from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.loop_engine.quality.policy import REQUIRED_REVIEW_AXES
from paperorchestra.loop_engine.quality.reviewer_independence import (
    _current_review_records,
    _reviewer_independence_acceptance,
    _reviewer_independence_check,
)
from paperorchestra.loop_engine.quality.utils import _file_sha256


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid_axis_scores(score: float = 82.0) -> dict[str, dict[str, object]]:
    return {axis: {"score": score, "justification": f"{axis} has enough evidence."} for axis in REQUIRED_REVIEW_AXES}


def _review_payload(tmp_path: Path, paper_sha: str, reviewer_label: str, *, stale: bool = False) -> dict:
    prompt = tmp_path / f"{reviewer_label}-prompt.json"
    provider = tmp_path / f"{reviewer_label}-provider.json"
    manifest = tmp_path / f"{reviewer_label}-lane.json"
    for path in (prompt, provider, manifest):
        path.write_text(path.name, encoding="utf-8")
    manuscript_sha = "0" * 64 if stale else paper_sha
    return {
        "schema_version": "paper-review/1",
        "manuscript_sha256": manuscript_sha,
        "axis_scores": _valid_axis_scores(),
        "summary": {"weaknesses": [], "top_improvements": []},
        "penalties": [],
        "review_provenance": {
            "schema_version": "review-provenance/1",
            "stage": "review",
            "manuscript_sha256": manuscript_sha,
            "reviewer_label": reviewer_label,
            "provider_name": "codex",
            "provider_command_digest": f"digest-{reviewer_label}",
            "prompt_trace_meta_path": str(prompt),
            "provider_identity_path": str(provider),
            "lane_manifest_path": str(manifest),
            "prompt_trace_meta_sha256": _file_sha256(prompt),
            "provider_identity_sha256": _file_sha256(provider),
            "lane_manifest_sha256": _file_sha256(manifest),
        },
    }


def test_current_review_records_keeps_only_current_valid_reviews(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("current manuscript", encoding="utf-8")
    current_sha = _file_sha256(paper)

    valid_a = _write_json(tmp_path / "review-a.json", _review_payload(tmp_path, current_sha, "reviewer-a"))
    valid_b = _write_json(tmp_path / "review-b.json", _review_payload(tmp_path, current_sha, "reviewer-b"))
    stale = _write_json(tmp_path / "stale.json", _review_payload(tmp_path, current_sha, "reviewer-old", stale=True))
    invalid = _write_json(tmp_path / "invalid.json", {"schema_version": "paper-review/1"})
    state = SimpleNamespace(
        artifacts=SimpleNamespace(latest_review_json=str(valid_a)),
        review_history=[
            SimpleNamespace(raw_path=str(valid_b)),
            SimpleNamespace(raw_path=str(stale)),
            SimpleNamespace(raw_path=str(invalid)),
        ],
    )

    records = _current_review_records(state, current_sha)

    assert [record["identity"] for record in records] == ["reviewer-a", "reviewer-b"]
    assert {record["sha256"] for record in records} == {_file_sha256(valid_a), _file_sha256(valid_b)}


def test_reviewer_independence_acceptance_requires_current_review_hashes_and_writer_provenance(tmp_path: Path) -> None:
    paper_sha = "a" * 64
    review = _write_json(tmp_path / "review.json", _review_payload(tmp_path, paper_sha, "reviewer-a"))
    writer = tmp_path / "writer-refiner.json"
    writer.write_text("writer provenance", encoding="utf-8")
    records = [{"path": str(review), "sha256": _file_sha256(review), "identity": "reviewer-a"}]

    assert _reviewer_independence_acceptance(tmp_path, paper_sha, records)["status"] == "missing"

    _write_json(
        tmp_path / ".paper-orchestra" / "reviewer-independence-acceptance.json",
        {
            "schema_version": "reviewer-independence-acceptance/1",
            "source": "independent_human_review",
            "manuscript_sha256": paper_sha,
            "review_artifacts": [{"path": str(review), "sha256": _file_sha256(review)}],
            "rationale": "Independent reviewer inspected the current review artifact.",
            "operator_label": "hk",
            "accepted_at": "2026-06-18T00:00:00+00:00",
            "writer_refiner_provenance": [{"path": str(writer), "sha256": _file_sha256(writer)}],
        },
    )

    assert _reviewer_independence_acceptance(tmp_path, paper_sha, records)["status"] == "pass"

    writer.write_text("changed", encoding="utf-8")
    stale = _reviewer_independence_acceptance(tmp_path, paper_sha, records)
    assert stale["status"] == "fail"
    assert stale["failing_codes"] == ["reviewer_independence_acceptance_stale"]


def test_reviewer_independence_check_passes_with_two_reviewers_without_override(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("current manuscript", encoding="utf-8")
    current_sha = _file_sha256(paper)
    review_a = _write_json(tmp_path / "review-a.json", _review_payload(tmp_path, current_sha, "reviewer-a"))
    review_b = _write_json(tmp_path / "review-b.json", _review_payload(tmp_path, current_sha, "reviewer-b"))
    state = SimpleNamespace(
        artifacts=SimpleNamespace(paper_full_tex=str(paper), latest_review_json=str(review_a)),
        review_history=[SimpleNamespace(raw_path=str(review_b))],
    )

    result = _reviewer_independence_check(tmp_path, state, quality_mode="claim_safe")

    assert result["status"] == "pass"
    assert result["distinct_reviewer_count"] == 2
    assert result["reviewers"] == ["reviewer-a", "reviewer-b"]
    assert "operator_override_used" not in result
