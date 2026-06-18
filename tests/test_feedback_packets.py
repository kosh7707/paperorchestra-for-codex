from __future__ import annotations

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, set_current_session
from paperorchestra.feedback.packet_context import _packet_has_human_needed_context
from paperorchestra.feedback.packet_plan_validation import _validate_current_operator_plan
from paperorchestra.feedback.packet_records import _artifact_by_role


def test_artifact_by_role_returns_first_matching_dict() -> None:
    packet = {
        "artifacts": [
            "not-a-record",
            {"role": "qa_loop_plan", "path": "first"},
            {"role": "qa_loop_plan", "path": "second"},
        ]
    }

    assert _artifact_by_role(packet, "qa_loop_plan") == {"role": "qa_loop_plan", "path": "first"}
    assert _artifact_by_role(packet, "missing") is None


def test_packet_has_human_needed_context_reads_probe_artifacts(tmp_path) -> None:
    human_needed = tmp_path / "human-needed.json"
    unreadable = tmp_path / "missing.json"
    write_json(human_needed, {"verdict": "human_needed"})
    packet = {
        "artifacts": [
            {"role": "qa_loop_plan", "path": str(unreadable)},
            {"role": "qa_loop_execution", "path": str(human_needed)},
        ]
    }

    assert _packet_has_human_needed_context(packet) is True


def test_validate_current_operator_plan_requires_human_needed_unless_review_context(tmp_path) -> None:
    session_id = "po-test"
    manuscript_hash = "abc123"
    set_current_session(tmp_path, session_id)
    write_json(
        artifact_path(tmp_path, "qa-loop.plan.json"),
        {
            "verdict": "continue",
            "session_id": session_id,
            "quality_eval_summary": {"manuscript_hash": manuscript_hash},
        },
    )

    _validate_current_operator_plan(
        cwd=tmp_path,
        session_id=session_id,
        current_manuscript_sha256=manuscript_hash,
        allow_operator_review_context=True,
    )
    with pytest.raises(ContractError, match="verdict=human_needed"):
        _validate_current_operator_plan(
            cwd=tmp_path,
            session_id=session_id,
            current_manuscript_sha256=manuscript_hash,
        )


def test_validate_current_operator_plan_rejects_stale_hash(tmp_path) -> None:
    session_id = "po-test"
    set_current_session(tmp_path, session_id)
    write_json(
        artifact_path(tmp_path, "qa-loop.plan.json"),
        {
            "verdict": "human_needed",
            "session_id": session_id,
            "quality_eval_summary": {"manuscript_hash": "old"},
        },
    )

    with pytest.raises(ContractError, match="stale"):
        _validate_current_operator_plan(
            cwd=tmp_path,
            session_id=session_id,
            current_manuscript_sha256="new",
        )
