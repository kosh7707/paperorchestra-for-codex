from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.feedback.human_needed_artifacts import _sha256_file
from paperorchestra.feedback.human_needed_paths import _attach_public_path_or_label
from paperorchestra.feedback.operator_contract import import_operator_feedback
from paperorchestra.feedback.operator_feedback_flow import apply_operator_feedback
from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.provider_base import BaseProvider


def apply_recorded_human_needed_answer(
    result: dict[str, Any],
    cwd: str | Path | None,
    *,
    packet_path: Path,
    feedback_path: Path,
    imported_feedback_output: str | Path | None,
    provider: BaseProvider | None,
    max_supervised_iterations: int,
    require_compile: bool,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    runtime_mode: str,
    citation_evidence_mode: str,
    citation_provider_name: str | None,
    citation_provider_command: str | None,
) -> None:
    imported_path, _imported = import_operator_feedback(
        cwd,
        packet_path=packet_path,
        feedback_path=feedback_path,
        output_path=imported_feedback_output,
    )
    execution_path, execution = apply_operator_feedback(
        cwd,
        provider or MockProvider(),
        imported_feedback_path=imported_path,
        max_supervised_iterations=max_supervised_iterations,
        require_compile=require_compile,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        runtime_mode=runtime_mode,
        citation_evidence_mode=citation_evidence_mode,
        citation_provider_name=citation_provider_name,
        citation_provider_command=citation_provider_command,
    )
    _attach_public_path_or_label(result, cwd, "imported_feedback_path", imported_path)
    result["imported_feedback_sha256"] = _sha256_file(imported_path)
    _attach_public_path_or_label(result, cwd, "operator_feedback_execution_path", execution_path)
    result["operator_feedback_execution_sha256"] = _sha256_file(execution_path)
    result["operator_feedback_execution_summary"] = {
        "verdict": execution.get("verdict"),
        "promotion_status": execution.get("promotion_status"),
        "promotion_reason": execution.get("promotion_reason"),
        "supervised_iteration_index": execution.get("supervised_iteration_index"),
        "supervised_remaining": execution.get("supervised_remaining"),
        "candidate_branch": execution.get("candidate_branch"),
    }
