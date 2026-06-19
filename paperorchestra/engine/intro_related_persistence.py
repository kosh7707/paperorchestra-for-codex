from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_text
from paperorchestra.core.models import SessionState
from paperorchestra.core.session import artifact_path, save_session
from paperorchestra.engine.completion_identity import (
    _lane_owner,
    _provider_name,
)
from paperorchestra.engine.intro_related_generation import IntroRelatedDraft
from paperorchestra.engine.reports import _blocking_issues, _issue_messages, _record_validation_report
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


def persist_intro_related_outputs(
    cwd: str | Path | None,
    state: SessionState,
    provider: BaseProvider,
    draft: IntroRelatedDraft,
    *,
    runtime_mode: str,
    allow_recoverable_contract_issues: bool,
) -> Path:
    state.latest_provider_name = _provider_name(provider)
    state.latest_runtime_mode = runtime_mode
    save_session(cwd, state)

    validation_path, _ = _record_validation_report(
        cwd,
        stage="intro_related",
        issues=draft.validation_issues,
        name="validation.intro_related.json",
        manuscript_text=draft.latex,
    )
    state.artifacts.latest_validation_json = str(validation_path)
    blocking_issues = _blocking_issues(draft.validation_issues)
    tolerated_recoverable_issues = (
        allow_recoverable_contract_issues
        and bool(blocking_issues)
        and {issue.code for issue in blocking_issues} <= {"citation_coverage_insufficient"}
    )
    if blocking_issues:
        state.notes.append(
            "Introduction/Related Work recoverable validation blockers: "
            + " | ".join(_issue_messages(blocking_issues))
        )
        if not tolerated_recoverable_issues:
            save_session(cwd, state)
            raise ContractError(
                "Introduction/Related Work output failed contract validation:\n- "
                + "\n- ".join(_issue_messages(blocking_issues))
            )
        draft = replace(
            draft,
            lane_notes=draft.lane_notes
            + [
                "Persisted a recoverable Introduction/Related Work candidate despite citation-coverage shortfall "
                "so the supervised QA/operator loop can repair it instead of aborting the live smoke early."
            ],
        )
    elif draft.validation_issues:
        state.notes.append(
            "Introduction/Related Work validation warnings: " + " | ".join(_issue_messages(draft.validation_issues))
        )

    state.notes.append(f"Validation report recorded: {validation_path.name}")
    path = artifact_path(cwd, "introduction_related_work.tex")
    write_text(path, draft.latex)
    lane_path = record_lane_manifest(
        cwd,
        stage="intro_related",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=draft.lane_type,
        owner=_lane_owner(draft.lane_type, draft.fallback_used),
        status="fallback_completed" if draft.fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or "", state.artifacts.citation_map_json or ""],
        output_artifacts=[str(path), str(validation_path)],
        fallback_used=draft.fallback_used,
        notes=draft.lane_notes,
    )
    state.artifacts.intro_related_tex = str(path)
    state.current_phase = "section_writing"
    state.active_artifact = "introduction_related_work.tex"
    state.notes.append("Introduction and Related Work drafted.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path
