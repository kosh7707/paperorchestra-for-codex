from __future__ import annotations

from pathlib import Path

from paperorchestra.feedback import operator_records
from paperorchestra.feedback.operator_contract import (
    OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION,
    OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION,
)
from paperorchestra.feedback.operator_issue_contract import OPERATOR_SOURCE


def test_build_operator_execution_record_preserves_imported_metadata(tmp_path: Path) -> None:
    imported_path = tmp_path / "operator_feedback.imported.json"
    imported_path.write_text("{}", encoding="utf-8")
    imported = {
        "packet_sha256": "sha256:packet",
        "translated_actions": ["tighten method"],
        "human_needed_answer": {"answer": "yes"},
        "operator_review_notes": {"notes": ["ok"]},
    }

    record = operator_records._build_operator_execution_record(
        imported_path,
        imported,
        current_sha="sha256:paper",
        max_supervised_iterations=3,
        intent="generate_new_operator_candidate",
    )

    assert record["schema_version"] == OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION
    assert record["event_type"] == "operator_feedback_cycle"
    assert record["source"] == OPERATOR_SOURCE
    assert record["imported_feedback_path"] == str(imported_path.resolve())
    assert record["packet_sha256"] == "sha256:packet"
    assert record["manuscript_sha256_before"] == "sha256:paper"
    assert record["supervised_max_iterations"] == 3
    assert record["candidate_branch"] == "generate_new_operator_candidate"
    assert record["promotion_status"] == "candidate_ready"
    assert record["attempts"] == []
    assert record["human_needed_answer"] == {"answer": "yes"}
    assert record["operator_review_notes"] == {"notes": ["ok"]}


def test_build_operator_attempt_record_includes_gate_and_preservation_fields() -> None:
    record = operator_records._build_operator_attempt_record(
        attempt_index=2,
        intent="generate_new_operator_candidate",
        candidate_result={
            "candidate_path": "/tmp/candidate.tex",
            "executor_failure_category": "none",
            "preserved_prior_after_contract_regression": True,
            "rejected_candidate_path": "/tmp/rejected.tex",
            "contract_regression_issue_count": 1,
        },
        candidate_sha_for_attempt="sha256:candidate",
        gate_passed=False,
        gate_reasons=["contract_regression_preserved_prior"],
        base_tier2_failures={"old"},
        candidate_tier2_failures={"old", "new"},
        new_tier2_failures=["new"],
        base_active_failures={"old"},
        candidate_active_failures={"new"},
        resolved_active_failures=["old"],
        active_tier2_metric_delta={"total_improved": False},
        protected_regressions=[{"code": "citation"}],
        verification_block={"validation_path": "validation.json"},
        incorporation=[{"id": "issue"}],
    )

    assert record["attempt_index"] == 2
    assert record["candidate_sha256"] == "sha256:candidate"
    assert record["base_tier2_failures"] == ["old"]
    assert record["candidate_tier2_failures"] == ["new", "old"]
    assert record["executor_path"] == "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper"
    assert record["preserved_prior_after_contract_regression"] is True
    assert record["rejected_candidate_path"] == "/tmp/rejected.tex"
    assert record["contract_regression_issue_count"] == 1


def test_build_operator_incorporation_report_and_verdict() -> None:
    report = operator_records._build_operator_incorporation_report(
        imported={"packet_sha256": "sha256:packet", "human_needed_answer": {"answer": "no"}},
        current_sha="sha256:before",
        after_sha="sha256:after",
        promotion_status="rolled_back",
        actionable_failure={"code": "blocked"},
        issues=[{"id": "issue"}],
    )

    assert report["schema_version"] == OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION
    assert report["source"] == OPERATOR_SOURCE
    assert report["packet_sha256"] == "sha256:packet"
    assert report["manuscript_sha256_before"] == "sha256:before"
    assert report["manuscript_sha256_after"] == "sha256:after"
    assert report["actionable_failure"] == {"code": "blocked"}
    assert report["human_needed_answer"] == {"answer": "no"}
    assert operator_records._operator_feedback_verdict(
        executor_crashed=True,
        promoted=True,
        plan={"verdict": "pass"},
    ) == "execution_error"
    assert operator_records._operator_feedback_verdict(
        executor_crashed=False,
        promoted=True,
        plan={"verdict": "pass"},
    ) == "pass"
    assert operator_records._operator_feedback_verdict(
        executor_crashed=False,
        promoted=False,
        plan={"verdict": "pass"},
    ) == "human_needed"
