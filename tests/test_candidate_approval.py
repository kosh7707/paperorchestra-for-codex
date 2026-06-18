from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import write_json
from paperorchestra.feedback import candidate_approval


def _approval_artifact(tmp_path: Path, role: str, *, candidate_sha: str = "candidate", nested: bool = False, blocked: bool = False) -> dict[str, str]:
    path = tmp_path / f"{role}.json"
    approval = {"status": "human_needed_candidate_ready", "candidate_sha256": f"sha256:{candidate_sha}"}
    progress = {"forward_progress": True}
    payload = {"candidate_approval": approval, "candidate_progress": progress}
    if nested:
        payload = {"candidate_result": payload, "attempts": []}
        if blocked:
            payload["attempts"] = [{"gate_reasons": ["citation_integrity_failed"]}]
    write_json(path, payload)
    return {"role": role, "path": str(path)}


def test_actionable_candidate_approval_prefers_operator_feedback_role(tmp_path: Path) -> None:
    packet = {
        "manuscript_sha256": "sha256:paper",
        "artifacts": [
            _approval_artifact(tmp_path, "qa_loop_execution", candidate_sha="qa-candidate"),
            _approval_artifact(tmp_path, "operator_feedback_execution", candidate_sha="op-candidate"),
        ],
    }

    assert candidate_approval.actionable_candidate_approval_role(packet) == "operator_feedback_execution"


def test_actionable_candidate_approval_ignores_current_hash_and_blocked_nested_attempt(tmp_path: Path) -> None:
    packet = {
        "manuscript_sha256": "sha256:paper",
        "artifacts": [
            _approval_artifact(tmp_path, "qa_loop_execution", candidate_sha="paper"),
            _approval_artifact(tmp_path, "operator_feedback_execution", candidate_sha="candidate", nested=True, blocked=True),
        ],
    }

    assert candidate_approval.actionable_candidate_approval_role(packet) is None


def test_candidate_approval_issues_for_role_filters_matching_source() -> None:
    issues = [
        {"source_artifact_role": "qa_loop_execution", "id": "qa"},
        {"source_artifact_role": "operator_feedback_execution", "id": "op"},
        "ignored",
    ]

    assert candidate_approval.candidate_approval_issues_for_role(issues, "qa_loop_execution") == [
        {"source_artifact_role": "qa_loop_execution", "id": "qa"}
    ]
    assert candidate_approval.candidate_approval_issues_for_role(issues, None) == []
