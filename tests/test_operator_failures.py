from __future__ import annotations

from paperorchestra.feedback import operator_failures, operator_gates


def test_operator_gates_facade_reexports_failure_helpers() -> None:
    assert operator_gates._compact_metric_delta_records is operator_failures._compact_metric_delta_records
    assert operator_gates._normalized_sha is operator_failures._normalized_sha
    assert operator_gates._actionable_failure is operator_failures._actionable_failure
    assert operator_gates._compact_operator_attempt_failure is operator_failures._compact_operator_attempt_failure
    assert operator_gates._compact_blocked_candidate_progress is operator_failures._compact_blocked_candidate_progress
    assert operator_gates._repeats_non_promotable_candidate is operator_failures._repeats_non_promotable_candidate
    assert operator_gates._operator_actionable_failure is operator_failures._operator_actionable_failure


def test_compact_operator_attempt_failure_keeps_only_code_count_diagnostics() -> None:
    payload = operator_failures._compact_operator_attempt_failure(
        [
            {
                "attempt_index": 2,
                "gate_passed": False,
                "gate_reasons": ["compile_failed", "compile_failed", ""],
                "new_tier2_failures": ["new"],
                "resolved_active_failures": ["old"],
                "candidate_active_failures": ["remaining"],
                "base_active_failures": ["old", "remaining"],
                "executor_failure_category": "runtime_error",
                "candidate_path": "/must/not/leak.tex",
                "active_tier2_metric_delta": {
                    "improvements": [{"code": "old", "before": 3, "after": 1, "delta": -2}],
                    "regressions": [{"code": "new", "before": 0, "after": 1, "delta": 1}],
                    "base_total": 3,
                    "candidate_total": 2,
                    "total_improved": True,
                },
            }
        ]
    )

    assert payload["attempt_index"] == 2
    assert payload["latest_gate_reasons"] == ["compile_failed"]
    assert payload["executor_failure_category"] == "runtime_error"
    assert payload["blocked_candidate_progress"]["metric_improvements"] == [
        {"after": 1, "before": 3, "code": "old", "delta": -2}
    ]
    assert "candidate_path" not in payload
    assert "must/not/leak" not in str(payload)


def test_compact_blocked_candidate_progress_returns_none_without_progress() -> None:
    assert operator_failures._compact_blocked_candidate_progress({"gate_passed": True}) is None
    assert operator_failures._compact_blocked_candidate_progress({"gate_passed": False, "gate_reasons": ["blocked"]}) is None


def test_repeats_non_promotable_candidate_ignores_promoted_or_reasonless_prior_attempts() -> None:
    assert (
        operator_failures._repeats_non_promotable_candidate(
            [
                {"candidate_sha256": "sha256:abc", "gate_passed": True, "gate_reasons": ["blocked"]},
                {"candidate_sha256": "abc", "gate_passed": False, "gate_reasons": []},
                {"candidate_sha256": "sha256:abc", "gate_passed": False, "gate_reasons": ["blocked"]},
            ],
            "abc",
        )
        is True
    )
    assert operator_failures._repeats_non_promotable_candidate([], "abc") is False


def test_operator_actionable_failure_adds_category_code_steps_and_execution_error() -> None:
    payload = operator_failures._operator_actionable_failure(
        ["operator", "author", "operator"],
        "candidate blocked",
        category="candidate_gate",
        code="blocked_candidate",
        attempts=[],
        execution_error="boom",
    )

    assert payload["owner_categories"] == ["author", "operator"]
    assert payload["execution_error"] == "boom"
    assert payload["category"] == "candidate_gate"
    assert payload["code"] == "blocked_candidate"
    assert len(payload["next_steps"]) == 3
