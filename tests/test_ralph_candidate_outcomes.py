from __future__ import annotations

import tempfile
from pathlib import Path

from paperorchestra.loop_engine.ralph.candidate_outcomes import (
    build_auto_commit_record,
    build_auto_commit_rejection_records,
    build_citation_support_rejection_records,
    classify_candidate_outcome,
    should_override_no_progress,
)


def test_classify_candidate_outcome_keeps_non_candidate_path_separate() -> None:
    assert classify_candidate_outcome(
        citation_candidate_applied=False,
        auto_commit_allowed=False,
        after_codes={"citation_support_unsupported"},
    ) == "none"
    assert classify_candidate_outcome(
        citation_candidate_applied=True,
        auto_commit_allowed=True,
        after_codes=set(),
    ) == "auto_commit"
    assert classify_candidate_outcome(
        citation_candidate_applied=True,
        auto_commit_allowed=False,
        after_codes={"citation_support_weak", "other"},
    ) == "citation_support_rejected"
    assert classify_candidate_outcome(
        citation_candidate_applied=True,
        auto_commit_allowed=False,
        after_codes={"citation_duplicate_support"},
    ) == "auto_commit_gate_rejected"


def test_build_auto_commit_record_hashes_candidate_and_sorts_codes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "candidate.tex"
        candidate.write_text("paper", encoding="utf-8")

        record = build_auto_commit_record(
            candidate_path=str(candidate),
            auto_commit_reason="strict_progress_without_new_failures",
            residual_citation_failures=["citation_support_weak"],
            after_codes={"z", "a"},
        )

    assert record["status"] == "committed_for_continued_qa"
    assert record["candidate_path"] == str(candidate)
    assert record["candidate_sha256"].startswith("sha256:")
    assert record["residual_citation_failures"] == ["citation_support_weak"]
    assert record["after_failing_codes"] == ["a", "z"]


def test_rejection_record_builders_preserve_existing_contract_strings() -> None:
    citation_support = build_citation_support_rejection_records(
        candidate_path="/tmp/candidate.tex",
        residual_citation_failures=["citation_support_unsupported"],
        auto_commit_reason="non_human_reviewable_citation_support_residuals",
    )
    auto_gate = build_auto_commit_rejection_records(
        candidate_path="/tmp/candidate.tex",
        auto_commit_reason="new_failure_codes",
        after_codes={"new", "old"},
    )

    assert citation_support["rollback"]["reason"] == "citation_support_approval_failed"
    assert citation_support["handoff"]["status"] == "human_needed_candidate_rejected_by_citation_support"
    assert citation_support["handoff"]["residual_citation_failures"] == ["citation_support_unsupported"]
    assert auto_gate["rollback"]["reason"] == "citation_candidate_auto_commit_blocked"
    assert auto_gate["rollback"]["failing_codes"] == ["new", "old"]
    assert auto_gate["handoff"]["status"] == "human_needed_candidate_rejected_by_auto_commit_gate"


def test_should_override_no_progress_matches_bridge_guard() -> None:
    assert should_override_no_progress(
        verdict="continue",
        actions_attempted=[{"code": "x"}],
        final_progress={"forward_progress": False},
        citation_candidate_applied=False,
        candidate_progress={"forward_progress": False},
    )
    assert not should_override_no_progress(
        verdict="continue",
        actions_attempted=[{"code": "x"}],
        final_progress={"forward_progress": False},
        citation_candidate_applied=True,
        candidate_progress={"forward_progress": True},
    )
    assert not should_override_no_progress(
        verdict="human_needed",
        actions_attempted=[{"code": "x"}],
        final_progress={"forward_progress": False},
        citation_candidate_applied=False,
        candidate_progress={},
    )
