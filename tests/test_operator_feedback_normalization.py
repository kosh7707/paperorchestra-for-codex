from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_json
from paperorchestra.feedback.normalization import normalize_operator_feedback_draft
from paperorchestra.feedback.operator_answer_metadata import HUMAN_NEEDED_METADATA_SCHEMA_VERSION


def _packet(tmp_path: Path, *, approval_role: str | None = None) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    if approval_role:
        approval_path = tmp_path / f"{approval_role}.json"
        write_json(
            approval_path,
            {
                "candidate_approval": {
                    "status": "human_needed_candidate_ready",
                    "candidate_sha256": "sha256:candidate",
                },
                "candidate_progress": {"forward_progress": True},
            },
        )
        artifacts.append({"role": approval_role, "path": str(approval_path)})
    return {
        "packet_sha256": "packet-sha",
        "manuscript_sha256": "manuscript-sha",
        "session_id": "session-one",
        "artifacts": artifacts,
    }


def _issue(source: str, key: str, severity: str, text: str) -> dict[str, str]:
    return {
        "source_artifact_role": source,
        "source_item_key": key,
        "target_section": "Related Work",
        "severity": severity,
        "rationale": text,
        "suggested_action": f"Repair {text}",
        "authority_class": "author_feedback",
    }


def test_normalize_feedback_defaults_to_generated_candidate_and_redacts_metadata(tmp_path: Path) -> None:
    metadata = {
        "schema_version": HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
        "session_id": "session-one",
        "answer": "redacted",
    }

    feedback = normalize_operator_feedback_draft(
        _packet(tmp_path),
        {
            "issues": [_issue("qa_loop_plan", "citation_missing", "major", "Citation is missing.")],
            "human_needed_answer": metadata,
        },
    )

    assert feedback["intent"] == "generate_new_operator_candidate"
    assert feedback["issues"][0]["owner_category"] == "bibliography"
    assert feedback["issues"][0]["id"].startswith("opfb-")
    assert feedback["issues"][0]["source"] == "codex_operator"
    assert feedback["human_needed_answer"] == metadata


def test_generated_candidate_issues_keep_top_three_by_severity_and_role(tmp_path: Path) -> None:
    feedback = normalize_operator_feedback_draft(
        _packet(tmp_path),
        {
            "intent": "generate_new_operator_candidate",
            "issues": [
                _issue("qa_loop_plan", "minor-plan", "minor", "Plan issue."),
                _issue("quality_eval", "block-quality", "blocker", "Evaluation issue."),
                _issue("citation_support_review", "major-cite", "major", "Citation issue."),
                _issue("figure_placement_review", "critical-figure", "critical", "Figure issue."),
            ],
        },
    )

    assert [issue["source_item_key"] for issue in feedback["issues"]] == [
        "critical-figure",
        "block-quality",
        "major-cite",
    ]


def test_approve_existing_candidate_without_ready_artifact_falls_back_to_generated_candidate(tmp_path: Path) -> None:
    feedback = normalize_operator_feedback_draft(
        _packet(tmp_path),
        {"intent": "approve_existing_candidate", "issues": []},
    )

    assert feedback["intent"] == "generate_new_operator_candidate"
    assert feedback["issues"][0]["source_item_key"] == "candidate_progress_without_candidate_approval"


def test_approve_existing_candidate_inserts_default_approval_issue(tmp_path: Path) -> None:
    feedback = normalize_operator_feedback_draft(
        _packet(tmp_path, approval_role="qa_loop_execution"),
        {"intent": "approve_existing_candidate", "issues": []},
    )

    assert feedback["intent"] == "approve_existing_candidate"
    issue = feedback["issues"][0]
    assert issue["source_artifact_role"] == "qa_loop_execution"
    assert issue["source_item_key"] == "candidate_approval"
    assert issue["target_section"] == "Whole manuscript"
    assert issue["owner_category"] == "author"
    assert issue["source"] == "codex_operator"
    assert issue["not_independent_human_review"] is True
    assert issue["id"].startswith("opfb-")


def test_normalize_feedback_rejects_unsupported_human_needed_metadata_schema(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="unsupported schema_version"):
        normalize_operator_feedback_draft(
            _packet(tmp_path),
            {
                "intent": "generate_new_operator_candidate",
                "human_needed_answer": {"schema_version": "human-needed-answer/0", "answer": "redacted"},
            },
        )


def test_normalize_feedback_validates_legacy_human_needed_answer_even_with_explicit_notes(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="raw/private answer"):
        normalize_operator_feedback_draft(
            _packet(tmp_path),
            {
                "intent": "generate_new_operator_candidate",
                "operator_review_notes": {"answer": "redacted"},
                "human_needed_answer": {"answer_text": "secret"},
            },
        )
