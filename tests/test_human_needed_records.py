from __future__ import annotations

from paperorchestra.feedback import human_needed, human_needed_records


def test_human_needed_facade_reexports_record_helpers() -> None:
    assert human_needed._action_id is human_needed_records._action_id
    assert human_needed._artifact_source is human_needed_records._artifact_source
    assert human_needed._draft_issue_for_action is human_needed_records._draft_issue_for_action
    assert human_needed._metadata_without_targets is human_needed_records._metadata_without_targets
    assert human_needed.feedback_draft is human_needed_records.feedback_draft
    assert human_needed.private_answer_payload is human_needed_records.private_answer_payload
    assert human_needed.public_answer_payload is human_needed_records.public_answer_payload
    assert human_needed.public_result_payload is human_needed_records.public_result_payload


def test_metadata_without_targets_binds_selected_handoff_source() -> None:
    packet = {
        "session_id": "session-1",
        "packet_sha256": "sha256:packet",
        "manuscript_sha256": "sha256:paper",
        "artifacts": [
            {"role": "qa_loop_plan", "sha256": "sha256:plan"},
            {"role": "qa_loop_execution", "sha256": "sha256:execution"},
        ],
    }

    metadata = human_needed_records._metadata_without_targets(
        packet=packet,
        packet_file_sha256="sha256:file",
        answer_sha256="sha256:answer",
        private_answer_artifact_sha256=None,
        decision_kind="generate_new_operator_candidate",
        handoff_type="general_operator_feedback",
        action={"id": "act-1"},
        candidate_role=None,
    )

    assert metadata["schema_version"] == "human-needed-answer-metadata/1"
    assert metadata["target_action_id"] == "act-1"
    assert metadata["selected_handoff_source"] == {"role": "qa_loop_plan", "sha256": "sha256:plan"}
    assert metadata["answer"] == "redacted"


def test_public_answer_and_result_payloads_are_redacted() -> None:
    metadata = {
        "schema_version": "human-needed-answer-metadata/1",
        "session_id": "session-1",
        "answer": "redacted",
    }

    public_payload = human_needed_records.public_answer_payload(metadata)
    result = human_needed_records.public_result_payload(public_payload)

    assert public_payload["schema_version"] == "human-needed-answer-public/1"
    assert public_payload["answer"] == "redacted"
    assert result["answer"] == "redacted"
    assert result["execution"] == "human_needed_answer_recorded"


def test_private_answer_payload_binds_packet_and_action_without_redaction() -> None:
    payload = human_needed_records.private_answer_payload(
        schema_version="human-needed-answer/1",
        recorded_at="2026-06-18T00:00:00Z",
        packet={"session_id": "session-1", "packet_sha256": "sha256:packet", "manuscript_sha256": "sha256:paper"},
        packet_file_sha256="sha256:file",
        answer_sha256="sha256:answer",
        answer="operator said yes",
        decision_kind="generate_new_operator_candidate",
        handoff_type="general_operator_feedback",
        action={"action_id": "act-2"},
    )

    assert payload == {
        "schema_version": "human-needed-answer/1",
        "recorded_at": "2026-06-18T00:00:00Z",
        "session_id": "session-1",
        "packet_sha256": "sha256:packet",
        "packet_file_sha256": "sha256:file",
        "manuscript_sha256": "sha256:paper",
        "answer_sha256": "sha256:answer",
        "answer": "operator said yes",
        "decision_kind": "generate_new_operator_candidate",
        "handoff_type": "general_operator_feedback",
        "target_action_id": "act-2",
    }


def test_feedback_draft_uses_candidate_approval_or_action_context() -> None:
    metadata = {"answer": "redacted", "decision_kind": "approve_existing_candidate"}
    approved = human_needed_records.feedback_draft(
        action=None,
        handoff_type="candidate_approval",
        decision_kind="approve_existing_candidate",
        candidate_role="qa_loop_execution",
        metadata=metadata,
    )
    rejected = human_needed_records.feedback_draft(
        action={"code": "manual_review", "target": "Section 2", "reason": "Needs author judgment."},
        handoff_type="general_operator_feedback",
        decision_kind="reject_candidate_with_reason",
        candidate_role=None,
        metadata=metadata,
    )

    assert approved["intent"] == "approve_existing_candidate"
    assert approved["issues"][0]["source_artifact_role"] == "qa_loop_execution"
    assert approved["issues"][0]["source_item_key"] == "candidate_approval"
    assert approved["human_needed_answer"] is metadata
    assert rejected["issues"][0]["source_artifact_role"] == "qa_loop_plan"
    assert rejected["issues"][0]["source_item_key"] == "manual_review"
    assert "Reject the currently exposed candidate" in rejected["issues"][0]["suggested_action"]
