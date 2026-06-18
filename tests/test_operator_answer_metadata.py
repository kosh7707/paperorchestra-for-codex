from __future__ import annotations

import json
from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback import operator_answer_metadata as answer
from paperorchestra.feedback import operator_contract
from paperorchestra.feedback.packet_artifacts import _file_sha256, _packet_sha256


HEX_A = "a" * 64
HEX_B = "b" * 64


def _packet_with_artifacts(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source = tmp_path / "qa_loop_execution.json"
    source.write_text('{"verdict":"human_needed"}', encoding="utf-8")
    plan = tmp_path / "qa_loop_plan.json"
    plan.write_text('{"repair_actions":[{"id":"act-1"}]}', encoding="utf-8")
    packet: dict[str, object] = {
        "schema_version": operator_contract.OPERATOR_PACKET_SCHEMA_VERSION,
        "session_id": "session-1",
        "manuscript_sha256": HEX_A,
        "artifacts": [
            {"role": "qa_loop_execution", "path": str(source), "sha256": _file_sha256(source)},
            {"role": "qa_loop_plan", "path": str(plan), "sha256": _file_sha256(plan)},
        ],
    }
    packet["packet_sha256"] = _packet_sha256(packet)
    packet_path = tmp_path / "operator_review_packet.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    return packet_path, packet


def _valid_metadata(packet_path: Path, packet: dict[str, object]) -> dict[str, object]:
    source = next(item for item in packet["artifacts"] if item["role"] == "qa_loop_execution")  # type: ignore[index]
    return {
        "schema_version": answer.HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION,
        "session_id": packet["session_id"],
        "packet_sha256": packet["packet_sha256"],
        "packet_file_sha256": _file_sha256(packet_path),
        "manuscript_sha256": packet["manuscript_sha256"],
        "answer_sha256": "sha256:" + HEX_B,
        "private_answer_artifact_sha256": HEX_A,
        "decision_kind": "approve_existing_candidate",
        "handoff_type": "candidate_approval",
        "target_action_id": "act-1",
        "target_issue_ids": ["issue-1"],
        "selected_handoff_source": {"role": "qa_loop_execution", "sha256": source["sha256"]},
        "answer": "redacted",
    }


def test_operator_contract_facade_exports_answer_metadata_helpers() -> None:
    assert operator_contract._contains_forbidden_human_needed_metadata is answer._contains_forbidden_human_needed_metadata
    assert operator_contract.validate_operator_review_notes is answer.validate_operator_review_notes
    assert operator_contract._validate_human_needed_answer_metadata is answer._validate_human_needed_answer_metadata


def test_review_notes_reject_raw_or_private_answer_fields() -> None:
    assert answer.validate_operator_review_notes({"decision": "ok", "nested": [{"answer": "redacted"}]}) == {
        "decision": "ok",
        "nested": [{"answer": "redacted"}],
    }

    with pytest.raises(ContractError, match="raw/private answer"):
        answer.validate_operator_review_notes({"nested": {"answer_text": "secret"}})
    with pytest.raises(ContractError, match="raw/private answer"):
        answer.validate_operator_review_notes({"answer": "not redacted"})


def test_human_needed_answer_metadata_normalizes_valid_public_metadata(tmp_path: Path) -> None:
    packet_path, packet = _packet_with_artifacts(tmp_path)
    metadata = _valid_metadata(packet_path, packet)

    normalized = answer._validate_human_needed_answer_metadata(
        metadata,
        packet,
        {"issue-1"},
        packet_path=packet_path,
        intent="approve_existing_candidate",
        imported_issue_roles={"qa_loop_execution"},
    )

    assert normalized is not None
    assert normalized["schema_version"] == answer.HUMAN_NEEDED_METADATA_SCHEMA_VERSION
    assert normalized["answer"] == "redacted"
    assert normalized["target_issue_ids"] == ["issue-1"]


def test_human_needed_answer_metadata_rejects_unbound_source_and_issue(tmp_path: Path) -> None:
    packet_path, packet = _packet_with_artifacts(tmp_path)
    metadata = _valid_metadata(packet_path, packet)
    metadata["selected_handoff_source"] = {"role": "qa_loop_execution", "sha256": "0" * 64}

    with pytest.raises(ContractError, match="not bound to the packet"):
        answer._validate_human_needed_answer_metadata(
            metadata,
            packet,
            {"issue-1"},
            packet_path=packet_path,
            intent="approve_existing_candidate",
            imported_issue_roles={"qa_loop_execution"},
        )

    metadata = _valid_metadata(packet_path, packet)
    metadata["target_issue_ids"] = ["missing-issue"]
    with pytest.raises(ContractError, match="do not match imported issues"):
        answer._validate_human_needed_answer_metadata(
            metadata,
            packet,
            {"issue-1"},
            packet_path=packet_path,
            intent="approve_existing_candidate",
            imported_issue_roles={"qa_loop_execution"},
        )


def test_human_needed_answer_metadata_rejects_private_fields_and_intent_mismatch(tmp_path: Path) -> None:
    packet_path, packet = _packet_with_artifacts(tmp_path)
    metadata = _valid_metadata(packet_path, packet)
    metadata["raw_answer"] = "secret"

    with pytest.raises(ContractError, match="unsupported fields"):
        answer._validate_human_needed_answer_metadata(
            metadata,
            packet,
            {"issue-1"},
            packet_path=packet_path,
            intent="approve_existing_candidate",
            imported_issue_roles={"qa_loop_execution"},
        )

    metadata = _valid_metadata(packet_path, packet)
    with pytest.raises(ContractError, match="does not match operator feedback intent"):
        answer._validate_human_needed_answer_metadata(
            metadata,
            packet,
            {"issue-1"},
            packet_path=packet_path,
            intent="reject_candidate_with_reason",
            imported_issue_roles={"qa_loop_execution"},
        )
