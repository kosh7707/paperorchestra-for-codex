from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.pipeline import refine_current_paper
from paperorchestra.feedback.operator_context import _write_operator_review_for_refiner
from paperorchestra.feedback.operator_contract import _read_packet
from paperorchestra.feedback.packet_artifacts import _file_sha256, _sha256_digest, _sha256_prefixed
from paperorchestra.feedback.packet_bindings import (
    _artifact_bound_manuscript_sha,
    _execution_payload_sha256,
    _normalized_sha,
)
from paperorchestra.feedback.packets import _artifact_by_role
from paperorchestra.runtime.providers import BaseProvider, ProviderError, TransientProviderError


def _load_packet_from_imported(imported: dict[str, Any]) -> dict[str, Any]:
    return _read_packet(imported.get("packet_path"))


def _packet_artifact_payload(packet: dict[str, Any], role: str) -> dict[str, Any] | None:
    record = _artifact_by_role(packet, role)
    if not record:
        return None
    payload = read_json(record["path"])
    return payload if isinstance(payload, dict) else None


def _operator_execution_matches_packet_manuscript(
    payload: dict[str, Any],
    packet_manuscript_sha256: str | None,
) -> bool:
    bound_sha = _artifact_bound_manuscript_sha("operator_feedback_execution", payload)
    packet_sha = _normalized_sha(packet_manuscript_sha256)
    return bool(bound_sha and packet_sha and bound_sha == packet_sha)


def _packet_prior_operator_attempts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract failed-attempt memory from packet-carried operator executions.

    Fresh smoke advances through separate operator-feedback cycles.  The next
    cycle's packet can carry the previous cycle's hash-bound execution artifact,
    so seed the new candidate attempt with those prior failures before writing
    the refiner review.  Prompt-visible memory still goes through the compact
    code/count/hash-only serializer.
    """
    payload = _packet_artifact_payload(packet, "operator_feedback_execution")
    packet_sha = str(packet.get("manuscript_sha256") or "")
    payloads: list[dict[str, Any]] = []
    if isinstance(payload, dict) and _operator_execution_matches_packet_manuscript(payload, packet_sha):
        payloads.append(payload)
    if isinstance(payload, dict):
        candidate_result = payload.get("candidate_result")
        source_execution = candidate_result.get("source_execution") if isinstance(candidate_result, dict) else None
        if isinstance(source_execution, dict) and _operator_execution_matches_packet_manuscript(source_execution, packet_sha):
            payloads.append(source_execution)
    attempts: list[dict[str, Any]] = []
    for payload_item in payloads:
        for attempt in payload_item.get("attempts") or []:
            if isinstance(attempt, dict) and attempt.get("gate_passed") is not True:
                attempts.append(attempt)
    return attempts


def _candidate_approval_source_role(imported: dict[str, Any]) -> str | None:
    roles = {
        str(issue.get("source_artifact_role") or "")
        for issue in imported.get("issues") or []
        if isinstance(issue, dict) and str(issue.get("source_artifact_role") or "") in {"qa_loop_execution", "operator_feedback_execution"}
    }
    if len(roles) > 1:
        raise ContractError("approve_existing_candidate feedback must target exactly one candidate approval source artifact")
    return next(iter(roles), None)


def _candidate_source_execution_from_packet(packet: dict[str, Any], preferred_role: str | None = None) -> tuple[dict[str, Any], str]:
    roles = (preferred_role,) if preferred_role else ("qa_loop_execution", "operator_feedback_execution")
    for role in roles:
        if role not in {"qa_loop_execution", "operator_feedback_execution"}:
            raise ContractError("approve_existing_candidate targets an unsupported candidate approval source artifact")
        payload = _packet_artifact_payload(packet, role)
        if isinstance(payload, dict) and isinstance(payload.get("candidate_approval"), dict):
            return payload, role
        if role == "operator_feedback_execution" and isinstance(payload, dict):
            candidate_result = payload.get("candidate_result")
            if isinstance(candidate_result, dict):
                source_execution = candidate_result.get("source_execution")
                if isinstance(source_execution, dict) and isinstance(source_execution.get("candidate_approval"), dict):
                    return source_execution, role
    raise ContractError("approve_existing_candidate requires candidate approval execution evidence")


def _ready_candidate_from_packet(packet: dict[str, Any], current_sha: str | None, *, source_artifact_role: str | None = None) -> dict[str, Any]:
    execution, execution_role = _candidate_source_execution_from_packet(packet, source_artifact_role)
    approval = execution.get("candidate_approval") if isinstance(execution, dict) else None
    progress = execution.get("candidate_progress") if isinstance(execution, dict) else None
    candidate_state = execution.get("candidate_state") if isinstance(execution, dict) else None
    restored_current_state = execution.get("restored_current_state") if isinstance(execution, dict) else None
    if not isinstance(approval, dict) or approval.get("status") != "human_needed_candidate_ready":
        raise ContractError("approve_existing_candidate requires human_needed_candidate_ready evidence")
    missing_approval = [
        key
        for key in (
            "candidate_path",
            "candidate_sha256",
            "base_manuscript_sha256",
            "source_execution_path",
            "source_execution_sha256",
            "created_at",
        )
        if not str(approval.get(key) or "").strip()
    ]
    if missing_approval:
        raise ContractError("approve_existing_candidate missing candidate_approval." + ", candidate_approval.".join(missing_approval))
    if not isinstance(progress, dict) or progress.get("forward_progress") is not True:
        raise ContractError("approve_existing_candidate requires candidate_progress.forward_progress=true")
    for key in ("before_failing_codes", "after_failing_codes"):
        if key not in progress:
            raise ContractError(f"approve_existing_candidate missing candidate_progress.{key}")
    before_progress_codes = {str(code) for code in progress.get("before_failing_codes") or []}
    after_progress_codes = {str(code) for code in progress.get("after_failing_codes") or []}
    citation_issue_delta = progress.get("citation_issue_delta")
    citation_issue_count_improved = isinstance(citation_issue_delta, int) and citation_issue_delta < 0
    if before_progress_codes and not (before_progress_codes - after_progress_codes) and not citation_issue_count_improved:
        raise ContractError("approve_existing_candidate requires resolved active blockers or reduced citation issue count")
    candidate_verification = candidate_state.get("verification") if isinstance(candidate_state, dict) else None
    restored_verification = restored_current_state.get("verification") if isinstance(restored_current_state, dict) else None
    if not isinstance(candidate_verification, dict) and not isinstance(restored_verification, dict):
        raise ContractError("approve_existing_candidate requires candidate_state.verification or restored_current_state.verification")
    candidate_path = Path(str(approval.get("candidate_path") or "")).resolve()
    if not candidate_path.exists() or not candidate_path.is_file():
        raise ContractError("approved QA candidate file is missing")
    expected_candidate = _sha256_digest(str(approval.get("candidate_sha256") or ""))
    actual_candidate = _file_sha256(candidate_path)
    if not expected_candidate or expected_candidate != actual_candidate:
        raise ContractError("approved QA candidate hash mismatch")
    expected_base = _sha256_digest(str(approval.get("base_manuscript_sha256") or ""))
    if expected_base and current_sha and expected_base != current_sha:
        raise ContractError("approved QA candidate base manuscript hash mismatch")
    expected_source_sha = str(approval.get("source_execution_sha256") or "")
    actual_source_sha = _execution_payload_sha256(execution)
    source_path = approval.get("source_execution_path")
    source_record = _artifact_by_role(packet, execution_role)
    if source_path and source_record:
        approved_source = Path(str(source_path)).resolve()
        packet_sources = {Path(str(source_record["path"])).resolve()}
        if source_record.get("original_path"):
            packet_sources.add(Path(str(source_record["original_path"])).resolve())
        # Operator-feedback executions can carry a nested candidate_result
        # produced by an earlier QA-loop execution.  In that shape, the
        # approval's source_execution_path legitimately points at the embedded
        # QA execution, not the outer operator-feedback packet artifact.  The
        # hash check below is the binding proof that the embedded source is the
        # exact approval source reviewed by the operator.
        embedded_operator_source = execution_role == "operator_feedback_execution" and expected_source_sha == actual_source_sha
        if approved_source not in packet_sources and not embedded_operator_source:
            raise ContractError("approved QA candidate source execution path mismatch")
    if expected_source_sha != actual_source_sha:
        raise ContractError("approved QA candidate source execution hash mismatch")
    return {
        "candidate_path": str(candidate_path),
        "candidate_sha256": _sha256_prefixed(actual_candidate),
        "candidate_approval": approval,
        "candidate_progress": progress,
        "candidate_state": candidate_state,
        "source_execution": execution,
        "executor_environment": "preexisting_candidate",
        "executor_path": "operator_feedback._ready_candidate_from_packet",
        "executor_trace_artifact": str(source_path),
        "executor_failure_category": "none",
        "executor_source_role": execution_role,
    }


def _stage_candidate_text_for_verification(cwd: str | Path | None, candidate_path: str | Path) -> str:
    state = load_session(cwd)
    candidate = Path(candidate_path).resolve()
    candidate_text = candidate.read_text(encoding="utf-8")
    state.artifacts.paper_full_tex = str(candidate)
    state.active_artifact = candidate.name
    save_session(cwd, state)
    return candidate_text


def _preserve_operator_candidate_for_attempt(
    cwd: str | Path | None,
    candidate_result: dict[str, Any],
    *,
    attempt_index: int,
) -> dict[str, Any]:
    candidate_path = candidate_result.get("candidate_path")
    if not candidate_path:
        return candidate_result
    source = Path(str(candidate_path)).resolve()
    if not source.exists() or not source.is_file():
        return candidate_result
    preserved = artifact_path(cwd, f"paper.operator-feedback.attempt-{attempt_index:02d}.candidate.tex")
    preserved.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    updated = dict(candidate_result)
    updated.setdefault("raw_candidate_path", str(source))
    updated["candidate_path"] = str(preserved)
    updated["candidate_sha256"] = _sha256_prefixed(_file_sha256(preserved))
    updated["candidate_preservation_path"] = str(preserved)
    return updated


def _promote_candidate_text(cwd: str | Path | None, candidate_path: str | Path, canonical_path: str | Path | None) -> str:
    if not canonical_path:
        raise ContractError("cannot promote candidate without a canonical manuscript path")
    canonical = Path(canonical_path).resolve()
    candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    canonical.write_text(candidate_text, encoding="utf-8")
    state = load_session(cwd)
    state.artifacts.paper_full_tex = str(canonical)
    state.active_artifact = canonical.name
    save_session(cwd, state)
    return candidate_text


def _generate_operator_candidate(
    cwd: str | Path | None,
    provider: BaseProvider,
    imported: dict[str, Any],
    *,
    require_compile: bool,
    runtime_mode: str,
    quality_mode: str,
    prior_attempts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    redacted_review_path = _write_operator_review_for_refiner(cwd, imported, prior_attempts=prior_attempts)
    state = load_session(cwd)
    previous_review = state.artifacts.latest_review_json
    state.artifacts.latest_review_json = str(redacted_review_path)
    save_session(cwd, state)
    try:
        result = refine_current_paper(
            cwd,
            provider,
            iterations=1,
            require_compile_for_accept=require_compile,
            runtime_mode=runtime_mode,
            claim_safe=quality_mode == "claim_safe",
            candidate_only=True,
        )
    finally:
        state = load_session(cwd)
        state.artifacts.latest_review_json = previous_review
        save_session(cwd, state)
    item = result[-1] if result else {}
    candidate_path = item.get("candidate_path")
    if candidate_path and Path(candidate_path).exists():
        candidate_text = Path(candidate_path).read_text(encoding="utf-8")
    else:
        state = load_session(cwd)
        candidate_path = state.artifacts.paper_full_tex
        candidate_text = Path(candidate_path).read_text(encoding="utf-8") if candidate_path else ""
    item = dict(item)
    item.setdefault("candidate_path", candidate_path)
    item.setdefault("candidate_sha256", _file_sha256(candidate_path))
    item["previous_review_json"] = previous_review
    item["candidate_text"] = candidate_text
    item.setdefault("executor_environment", "in_process")
    item.setdefault("executor_path", "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper")
    item.setdefault("executor_trace_artifact", str(redacted_review_path))
    item.setdefault("executor_failure_category", "none")
    return item


def _executor_failure_category(exc: Exception) -> str:
    if isinstance(exc, TransientProviderError):
        return "provider_transient_retry_exhausted"
    if isinstance(exc, ProviderError):
        return "provider_error"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ContractError):
        message = str(exc).lower()
        if "extract" in message or "latex" in message or "json" in message:
            return "extraction_failed"
        return "contract_error"
    return "unexpected_exception"


def _failed_operator_candidate_result(cwd: str | Path | None, exc: Exception, *, trace_artifact: str | None = None) -> dict[str, Any]:
    state = load_session(cwd)
    candidate_path = state.artifacts.paper_full_tex
    if trace_artifact is None:
        trace_path = artifact_path(cwd, "operator_feedback.executor-error.json")
        write_json(
            trace_path,
            {
                "schema_version": "operator-feedback-executor-error/1",
                "recorded_at": utc_now_iso(),
                "executor_environment": "in_process",
                "executor_path": "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper",
                "executor_failure_category": _executor_failure_category(exc),
                "error_type": type(exc).__name__,
            },
        )
        trace_artifact = str(trace_path)
    return {
        "iteration": 1,
        "accepted": False,
        "candidate_only": True,
        "candidate_path": candidate_path,
        "candidate_sha256": _file_sha256(candidate_path),
        "candidate_text": Path(candidate_path).read_text(encoding="utf-8") if candidate_path and Path(candidate_path).exists() else "",
        "executor_environment": "in_process",
        "executor_path": "operator_feedback._generate_operator_candidate->pipeline.refine_current_paper",
        "executor_trace_artifact": trace_artifact,
        "executor_failure_category": _executor_failure_category(exc),
        "executor_error_type": type(exc).__name__,
    }
