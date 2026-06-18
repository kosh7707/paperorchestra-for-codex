from __future__ import annotations

from paperorchestra.feedback.operator_candidate_hard_gate import _candidate_hard_gate
from paperorchestra.feedback.operator_candidate_progress import (
    _candidate_reduces_citation_issue_count,
    _catastrophic_review_regression,
)
from paperorchestra.feedback.operator_quality_codes import _quality_failing_codes, _tier_failing_codes


def test_quality_failing_codes_and_tier_codes_are_deduped_and_status_scoped() -> None:
    quality = {
        "tiers": {
            "tier_0_preconditions": {"status": "pass", "failing_codes": ["ignored"]},
            "tier_2_claim_safety": {"status": "fail", "failing_codes": ["a", "b", "a"]},
            "tier_3_scholarly": {"status": "warn", "failing_codes": ["c"]},
        }
    }

    assert _quality_failing_codes(quality) == ["a", "b", "c"]
    assert _tier_failing_codes(quality, "tier_2_claim_safety") == ["a", "b"]
    assert _tier_failing_codes(None, "tier_2_claim_safety") == []


def test_candidate_progress_and_catastrophic_regression_helpers() -> None:
    assert _candidate_reduces_citation_issue_count(
        {"candidate_progress": {"forward_progress": True, "citation_issue_delta": -1}}
    )
    assert not _candidate_reduces_citation_issue_count(
        {"candidate_progress": {"forward_progress": True, "citation_issue_delta": 0}}
    )
    assert _catastrophic_review_regression({"score_before": 80, "score_after": 60})
    assert _catastrophic_review_regression(
        {"axis_scores_before": {"clarity": 80}, "axis_scores_after": {"clarity": 40}}
    )
    assert not _catastrophic_review_regression({"score_before": 80, "score_after": 78})


def test_candidate_hard_gate_collects_expected_fail_closed_reasons() -> None:
    ok, reasons = _candidate_hard_gate(
        validation_payload={"ok": False},
        compile_payload={"ok": False},
        quality_eval={"tiers": {"tier_0_preconditions": {"status": "fail"}, "tier_1_structural": {"status": "fail"}}},
        base_quality_eval=None,
        quality_mode="claim_safe",
        incorporation=[{"status": "not_reflected"}],
        candidate_result={"executor_failure_category": "runtime", "score_before": 90, "score_after": 50},
        require_issue_progress=True,
        manuscript_changed=False,
        new_tier2_failures=["new_code"],
        base_active_failures=["old_code"],
        resolved_active_failures=[],
        protected_supported_citation_regressions=[{"key": "A"}],
    )

    assert not ok
    assert reasons == [
        "no_textual_change",
        "executor_crashed",
        "validation_failed",
        "compile_failed",
        "tier0_failed",
        "tier1_failed",
        "tier2_claim_safety_new_failures",
        "protected_supported_citation_regression",
        "active_blocker_metric_progress_missing",
        "issue_progress_missing",
        "reviewer_catastrophic_regression",
    ]
