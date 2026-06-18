from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path
from paperorchestra.feedback import human_needed_records as _records
from paperorchestra.feedback.human_needed_paths import _attach_public_path_or_label, _private_answer_path
from paperorchestra.feedback.normalization import normalize_operator_feedback_draft

HUMAN_NEEDED_ANSWER_SCHEMA_VERSION = "human-needed-answer/1"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _packet_file_sha256_after_canonical_validation(packet_path: Path, packet: dict[str, Any]) -> str:
    """Return the packet file hash after rejecting non-canonical packet bytes.

    The packet's embedded packet_sha256 protects semantic JSON contents.  The
    human-needed answer also binds to the exact file handed to the operator, so
    whitespace-only post-generation edits must not silently pass as the reviewed
    artifact.
    """

    text = packet_path.read_text(encoding="utf-8")
    if text != _canonical_json(packet):
        raise ContractError("operator review packet file hash does not match canonical contents")
    return _sha256_file(packet_path)


def _write_private_answer_if_allowed(
    cwd: str | Path | None,
    *,
    answer: str,
    packet: dict[str, Any],
    packet_file_sha256: str,
    decision_kind: str,
    handoff_type: str,
    action: dict[str, Any] | None,
    output_answer: str | Path | None,
    redacted_answer_only: bool,
) -> tuple[str, str | None]:
    answer_sha256 = _sha256_text(answer)
    raw_path = _private_answer_path(
        cwd,
        str(packet.get("session_id") or "unknown-session"),
        f"answer-{answer_sha256[:16]}",
        output_answer,
        redacted_answer_only=redacted_answer_only,
    )
    if raw_path is None:
        return answer_sha256, None

    raw_payload = _records.private_answer_payload(
        schema_version=HUMAN_NEEDED_ANSWER_SCHEMA_VERSION,
        recorded_at=utc_now_iso(),
        packet=packet,
        packet_file_sha256=packet_file_sha256,
        answer_sha256=answer_sha256,
        answer=answer,
        decision_kind=decision_kind,
        handoff_type=handoff_type,
        action=action,
    )
    write_json(raw_path, raw_payload)
    return answer_sha256, _sha256_file(raw_path)


def _write_public_answer_artifacts(
    cwd: str | Path | None,
    *,
    packet: dict[str, Any],
    packet_file_sha256: str,
    answer_sha256: str,
    private_answer_artifact_sha256: str | None,
    decision_kind: str,
    handoff_type: str,
    action: dict[str, Any] | None,
    candidate_role: str | None,
    output_feedback: str | Path | None,
) -> tuple[dict[str, Any], Path]:
    metadata = _records._metadata_without_targets(
        packet=packet,
        packet_file_sha256=packet_file_sha256,
        answer_sha256=answer_sha256,
        private_answer_artifact_sha256=private_answer_artifact_sha256,
        decision_kind=decision_kind,
        handoff_type=handoff_type,
        action=action,
        candidate_role=candidate_role,
    )
    draft = _records.feedback_draft(
        action=action,
        handoff_type=handoff_type,
        decision_kind=decision_kind,
        candidate_role=candidate_role,
        metadata=metadata,
    )
    feedback = normalize_operator_feedback_draft(packet, draft)
    metadata["target_issue_ids"] = [str(issue.get("id") or "") for issue in feedback.get("issues") or [] if str(issue.get("id") or "")]
    feedback["human_needed_answer"] = dict(metadata)

    feedback_path = Path(output_feedback).resolve() if output_feedback else artifact_path(cwd, "human_needed.operator_feedback.json")
    write_json(feedback_path, feedback)

    public_answer_artifact = artifact_path(cwd, "human_needed.answer.public.json")
    public_payload = _records.public_answer_payload(metadata)
    write_json(public_answer_artifact, public_payload)

    result = _records.public_result_payload(public_payload)
    _attach_public_path_or_label(result, cwd, "feedback_path", feedback_path)
    result["feedback_sha256"] = _sha256_file(feedback_path)
    _attach_public_path_or_label(result, cwd, "public_answer_artifact", public_answer_artifact)
    result["public_answer_artifact_sha256"] = _sha256_file(public_answer_artifact)
    return result, feedback_path
