from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path
from paperorchestra.feedback import operator_answer_metadata as _answer_metadata
from paperorchestra.feedback import operator_issue_contract as _issues
from paperorchestra.feedback.operator_contract_constants import (
    OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION,
    OPERATOR_FEEDBACK_SCHEMA_VERSION,
)
from paperorchestra.feedback.operator_packet_io import _read_packet
from paperorchestra.feedback.packet_artifacts import _file_sha256
from paperorchestra.feedback.packet_artifact_validation import _validate_operator_packet_artifact_bindings
from paperorchestra.feedback.packet_context import _packet_has_human_needed_context


def import_operator_feedback(
    cwd: str | Path | None,
    *,
    packet_path: str | Path,
    feedback_path: str | Path,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    packet_path = Path(packet_path).resolve()
    feedback_path = Path(feedback_path).resolve()
    packet = _read_packet(packet_path)
    if not _packet_has_human_needed_context(packet):
        raise ContractError(
            "operator review packet does not include terminal human_needed plan "
            "or latest human_needed QA/operator-feedback execution evidence"
        )
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=str(packet.get("manuscript_sha256") or ""),
    )
    feedback = _validated_feedback(feedback_path, packet)
    intent = _issues._normalize_operator_intent(feedback)
    issues = feedback.get("issues")
    if not isinstance(issues, list) or not issues:
        raise ContractError("operator feedback must include one or more issues")
    imported_issues = [_issues._validate_operator_issue(issue, packet) for issue in issues if isinstance(issue, dict)]
    if len(imported_issues) != len(issues):
        raise ContractError("operator feedback issues must all be JSON objects")
    human_needed_answer = _answer_metadata._validate_human_needed_answer_metadata(
        feedback.get("human_needed_answer"),
        packet,
        {str(issue.get("id") or "") for issue in imported_issues},
        packet_path=packet_path,
        intent=intent,
        imported_issue_roles={str(issue.get("source_artifact_role") or "") for issue in imported_issues},
    )
    operator_review_notes = None
    if "operator_review_notes" in feedback:
        operator_review_notes = _answer_metadata.validate_operator_review_notes(feedback.get("operator_review_notes"))
    imported = _imported_feedback_payload(
        packet=packet,
        feedback=feedback,
        packet_path=packet_path,
        feedback_path=feedback_path,
        intent=intent,
        imported_issues=imported_issues,
    )
    if operator_review_notes is not None:
        imported["operator_review_notes"] = operator_review_notes
    if human_needed_answer is not None:
        imported["human_needed_answer"] = human_needed_answer
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "operator_feedback.imported.json")
    write_json(path, imported)
    return path, imported


def _validated_feedback(feedback_path: Path, packet: dict[str, Any]) -> dict[str, Any]:
    feedback = read_json(feedback_path)
    if not isinstance(feedback, dict):
        raise ContractError("operator feedback must be a JSON object")
    if feedback.get("schema_version") != OPERATOR_FEEDBACK_SCHEMA_VERSION:
        raise ContractError("operator feedback has an unsupported schema_version")
    if feedback.get("source") != _issues.OPERATOR_SOURCE or feedback.get("not_independent_human_review") is not True:
        raise ContractError("operator feedback must be labeled source=codex_operator and not_independent_human_review=true")
    if feedback.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("operator feedback packet_sha256 does not match packet")
    if feedback.get("manuscript_sha256") != packet.get("manuscript_sha256"):
        raise ContractError("operator feedback manuscript_sha256 does not match packet")
    return feedback


def _imported_feedback_payload(
    *,
    packet: dict[str, Any],
    feedback: dict[str, Any],
    packet_path: Path,
    feedback_path: Path,
    intent: str,
    imported_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    imported = {
        "schema_version": OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION,
        "imported_at": utc_now_iso(),
        "session_id": packet.get("session_id"),
        "source": _issues.OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "packet_path": str(packet_path),
        "packet_sha256": packet.get("packet_sha256"),
        "feedback_path": str(feedback_path),
        "feedback_sha256": _file_sha256(feedback_path),
        "manuscript_sha256": packet.get("manuscript_sha256"),
        "review_scope": packet.get("review_scope"),
        "intent": intent,
        "issues": imported_issues,
        "translated_actions": [_issues._action_for_issue(issue) for issue in imported_issues],
    }
    if isinstance(feedback.get("rendered_pdf_no_issues"), dict):
        imported["rendered_pdf_no_issues"] = dict(feedback["rendered_pdf_no_issues"])
    return imported
