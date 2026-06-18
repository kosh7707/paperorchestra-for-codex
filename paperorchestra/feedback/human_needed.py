from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session
from paperorchestra.feedback.human_needed_artifacts import (
    _packet_file_sha256_after_canonical_validation,
    _sha256_file,
    _write_private_answer_if_allowed,
    _write_public_answer_artifacts,
)
from paperorchestra.feedback.human_needed_decision import (
    _classify_action,
    _human_needed_actions,
    _resolve_decision_kind,
    _select_action,
)
from paperorchestra.feedback.human_needed_paths import _attach_public_path_or_label
from paperorchestra.feedback.operator_feedback_flow import apply_operator_feedback
from paperorchestra.feedback.operator_contract import (
    _read_packet,
    build_operator_review_packet,
    import_operator_feedback,
)
from paperorchestra.feedback.candidate_approval_roles import actionable_candidate_approval_role
from paperorchestra.feedback.packet_artifacts import _file_sha256
from paperorchestra.feedback.packet_artifact_validation import _validate_operator_packet_artifact_bindings
from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.provider_base import BaseProvider
def record_human_needed_answer(
    cwd: str | Path | None,
    answer: str,
    *,
    packet_path: str | Path | None = None,
    review_scope: str | None = None,
    intent: str | None = None,
    action_id: str | None = None,
    output_answer: str | Path | None = None,
    output_feedback: str | Path | None = None,
    redacted_answer_only: bool = False,
    apply: bool = False,
    imported_feedback_output: str | Path | None = None,
    provider: BaseProvider | None = None,
    max_supervised_iterations: int = 1,
    require_compile: bool = False,
    quality_mode: str = "claim_safe",
    max_iterations: int = 10,
    require_live_verification: bool = False,
    accept_mixed_provenance: bool = False,
    runtime_mode: str = "compatibility",
    citation_evidence_mode: str = "web",
    citation_provider_name: str | None = None,
    citation_provider_command: str | None = None,
) -> dict[str, Any]:
    answer = str(answer or "")
    if not answer.strip():
        raise ContractError("human_needed answer must not be empty")

    if packet_path is None:
        packet_path_obj, packet = build_operator_review_packet(cwd, review_scope=review_scope)
    else:
        packet_path_obj = Path(packet_path).resolve()
        packet = _read_packet(packet_path_obj)
    packet_file_sha256 = _packet_file_sha256_after_canonical_validation(packet_path_obj, packet)

    state = load_session(cwd)
    current_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    if packet.get("manuscript_sha256") != current_manuscript_sha:
        raise ContractError("operator review packet manuscript hash is stale for the current session")
    assert current_manuscript_sha is not None
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=current_manuscript_sha,
    )

    candidate_role = actionable_candidate_approval_role(packet)
    decision_kind = _resolve_decision_kind(answer, intent, candidate_role=candidate_role)
    candidate_role = candidate_role if decision_kind == "approve_existing_candidate" else None
    action = _select_action(_human_needed_actions(packet), action_id, candidate_role=candidate_role)
    handoff_type = _classify_action(action, candidate_role=candidate_role)
    answer_sha256, private_answer_artifact_sha256 = _write_private_answer_if_allowed(
        cwd,
        answer=answer,
        packet=packet,
        packet_file_sha256=packet_file_sha256,
        decision_kind=decision_kind,
        handoff_type=handoff_type,
        action=action,
        output_answer=output_answer,
        redacted_answer_only=redacted_answer_only,
    )
    result, feedback_path = _write_public_answer_artifacts(
        cwd,
        packet=packet,
        packet_file_sha256=packet_file_sha256,
        answer_sha256=answer_sha256,
        private_answer_artifact_sha256=private_answer_artifact_sha256,
        decision_kind=decision_kind,
        handoff_type=handoff_type,
        action=action,
        candidate_role=candidate_role,
        output_feedback=output_feedback,
    )
    _attach_public_path_or_label(result, cwd, "packet_path", packet_path_obj)
    if apply:
        imported_path, _imported = import_operator_feedback(
            cwd,
            packet_path=packet_path_obj,
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
    return result
