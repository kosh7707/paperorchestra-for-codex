from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import load_session, save_session
from paperorchestra.engine.outline_stage import generate_outline
from paperorchestra.engine.planning_payloads import (
    _author_facing_writer_brief_block,
    _filter_planning_payloads_for_sections,
    _planning_payloads_for_prompt,
    _validate_author_facing_writer_brief,
    _writer_brief_from_planning,
)
from paperorchestra.manuscript.narrative_artifacts import write_planning_artifacts
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


def _append_unique_note(state, note: str, *, dedupe_window: int = 5) -> bool:
    if not note:
        return False
    if note in state.notes[-dedupe_window:]:
        return False
    state.notes.append(note)
    return True


def plan_narrative_and_claims(
    cwd: str | Path | None,
    provider: BaseProvider | None = None,
    *,
    runtime_mode: str = "compatibility",
) -> dict[str, Path]:
    state = load_session(cwd)
    paths = write_planning_artifacts(cwd)
    lane_path = record_lane_manifest(
        cwd,
        stage="narrative_planning",
        role="Narrative Claim Planner",
        runtime_mode=runtime_mode,
        lane_type="ralph",
        owner="paperorchestra",
        status="completed",
        input_artifacts=[
            state.artifacts.outline_json or "",
            state.artifacts.citation_map_json or "",
            state.artifacts.references_bib or "",
            state.inputs.idea_path,
            state.inputs.experimental_log_path,
            state.inputs.template_path,
        ],
        output_artifacts=[str(path) for path in paths.values()],
        fallback_used=False,
        notes=["Deterministic conservative narrative/claim/citation placement planning artifacts recorded."],
    )
    state = load_session(cwd)
    state.current_phase = "narrative_planning"
    state.active_artifact = "narrative_plan.json"
    _append_unique_note(state, "Plot and literature completed in parallel before narrative planning.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return paths


__all__ = [
    "_author_facing_writer_brief_block",
    "_filter_planning_payloads_for_sections",
    "_planning_payloads_for_prompt",
    "_validate_author_facing_writer_brief",
    "_writer_brief_from_planning",
    "generate_outline",
    "plan_narrative_and_claims",
]
