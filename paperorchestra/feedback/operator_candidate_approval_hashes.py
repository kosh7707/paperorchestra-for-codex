from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.feedback.packet_artifacts import _file_sha256, _sha256_digest
from paperorchestra.feedback.packet_bindings import _execution_payload_sha256
from paperorchestra.feedback.packets import _artifact_by_role


def _verified_candidate_file(approval: dict[str, Any]) -> tuple[Path, str]:
    candidate_path = Path(str(approval.get("candidate_path") or "")).resolve()
    if not candidate_path.exists() or not candidate_path.is_file():
        raise ContractError("approved QA candidate file is missing")
    expected = _sha256_digest(str(approval.get("candidate_sha256") or ""))
    actual = _file_sha256(candidate_path)
    if not expected or expected != actual:
        raise ContractError("approved QA candidate hash mismatch")
    return candidate_path, actual


def _verify_base_hash(approval: dict[str, Any], current_sha: str | None) -> None:
    expected = _sha256_digest(str(approval.get("base_manuscript_sha256") or ""))
    if expected and current_sha and expected != current_sha:
        raise ContractError("approved QA candidate base manuscript hash mismatch")


def _verify_source_binding(
    *,
    packet: dict[str, Any],
    execution: dict[str, Any],
    execution_role: str,
    approval: dict[str, Any],
) -> None:
    expected_sha = str(approval.get("source_execution_sha256") or "")
    actual_sha = _execution_payload_sha256(execution)
    source_path = approval.get("source_execution_path")
    source_record = _artifact_by_role(packet, execution_role)
    if source_path and source_record:
        approved_source = Path(str(source_path)).resolve()
        packet_sources = {Path(str(source_record["path"])).resolve()}
        if source_record.get("original_path"):
            packet_sources.add(Path(str(source_record["original_path"])).resolve())
        embedded_operator_source = execution_role == "operator_feedback_execution" and expected_sha == actual_sha
        if approved_source not in packet_sources and not embedded_operator_source:
            raise ContractError("approved QA candidate source execution path mismatch")
    if expected_sha != actual_sha:
        raise ContractError("approved QA candidate source execution hash mismatch")
