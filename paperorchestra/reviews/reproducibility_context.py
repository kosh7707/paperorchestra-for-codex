from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.reviews.reproducibility_artifacts import (
    _has_mock_watermark,
    _note_occurrence_count,
    _prompt_trace_files,
    _read_json_if_exists,
)
from paperorchestra.reviews.reproducibility_citations import (
    _citation_registry_live_provenance,
    _citation_support_review_provenance,
    _citation_surface_health,
    _mock_registry_entry_count,
)
from paperorchestra.reviews.reproducibility_validation import (
    _strict_content_gate_issues,
    _strict_content_gates_enabled,
    _validation_warning_reports,
)
from paperorchestra.runtime.parity import build_lane_manifest_summary


@dataclass(frozen=True)
class ReproducibilityAuditContext:
    state: Any
    lane_summary: dict[str, Any]
    session_artifact_dir: Path | None
    runtime_parity: dict[str, Any] | None
    provider_identity: dict[str, Any] | None
    compile_report: dict[str, Any] | None
    prompt_trace_dir: str | None
    prompt_files: list[Path]
    mock_registry_count: int
    citation_live_provenance: dict[str, Any]
    citation_support_review_provenance: dict[str, Any]
    citation_surface: dict[str, Any]
    validation_warning_reports: list[dict[str, Any]]
    validation_warning_count: int
    strict_content_gates: bool
    strict_content_gate_issues: list[dict[str, Any]]
    refinement_compile_preservation_count: int
    verification_invoked: bool
    paper_has_mock_watermark: bool


def collect_reproducibility_audit_context(cwd: str | Path | None) -> ReproducibilityAuditContext:
    state = load_session(cwd)
    lane_summary = build_lane_manifest_summary(cwd)
    session_artifact_dir = _session_artifact_dir(state)
    runtime_parity = _runtime_parity_payload(state, session_artifact_dir)
    provider_identity = _read_json_if_exists(state.artifacts.latest_provider_identity_json)
    compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
    prompt_trace_dir = state.artifacts.latest_prompt_trace_dir or (
        str(session_artifact_dir / "prompts") if session_artifact_dir else None
    )
    prompt_files = _prompt_trace_files(prompt_trace_dir)
    citation_live_provenance = _citation_registry_live_provenance(
        state.artifacts.citation_registry_json,
        state.artifacts.paper_full_tex,
    )
    citation_surface = _citation_surface_health(state)
    validation_warning_reports = _validation_warning_reports(state, session_artifact_dir)
    strict_content_gates = _strict_content_gates_enabled()
    strict_content_gate_issues = _strict_content_gate_issues(state, session_artifact_dir) if strict_content_gates else []
    return ReproducibilityAuditContext(
        state=state,
        lane_summary=lane_summary,
        session_artifact_dir=session_artifact_dir,
        runtime_parity=runtime_parity,
        provider_identity=provider_identity,
        compile_report=compile_report,
        prompt_trace_dir=prompt_trace_dir,
        prompt_files=prompt_files,
        mock_registry_count=_mock_registry_entry_count(state.artifacts.citation_registry_json),
        citation_live_provenance=citation_live_provenance,
        citation_support_review_provenance=_citation_support_review_provenance(cwd, state, session_artifact_dir),
        citation_surface=citation_surface,
        validation_warning_reports=validation_warning_reports,
        validation_warning_count=sum(item["warning_count"] for item in validation_warning_reports),
        strict_content_gates=strict_content_gates,
        strict_content_gate_issues=strict_content_gate_issues,
        refinement_compile_preservation_count=_note_occurrence_count(
            state.notes,
            "Compile-failed refinement iteration",
        ),
        verification_invoked=state.latest_verify_mode is not None,
        paper_has_mock_watermark=_has_mock_watermark(state.artifacts.paper_full_tex),
    )


def _session_artifact_dir(state: Any) -> Path | None:
    if not state.artifacts.paper_full_tex:
        return None
    return Path(state.artifacts.paper_full_tex).resolve().parent


def _runtime_parity_payload(state: Any, session_artifact_dir: Path | None) -> dict[str, Any] | None:
    runtime_parity = _read_json_if_exists(state.artifacts.latest_runtime_parity_json)
    if runtime_parity is None and session_artifact_dir is not None:
        runtime_parity = _read_json_if_exists(session_artifact_dir / "runtime-parity.json")
    return runtime_parity
