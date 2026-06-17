from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion import _lane_owner
from paperorchestra.engine.research_discovery import _build_candidate_payload
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.providers import BaseProvider


def discover_papers(
    cwd: str | Path | None,
    provider: BaseProvider | None = None,
    mode: str = "model",
    *,
    runtime_mode: str = "compatibility",
) -> Path:
    state = load_session(cwd)
    if not state.artifacts.outline_json:
        raise ContractError("Generate outline.json before discovering papers.")
    outline = read_json(state.artifacts.outline_json)
    payload, lane_type, fallback_used, lane_notes = _build_candidate_payload(
        outline,
        state,
        provider,
        mode,
        runtime_mode=runtime_mode,
        cwd=cwd,
    )

    if "macro_candidates" not in payload or "micro_candidates" not in payload:
        raise ContractError("candidate discovery output must contain macro_candidates and micro_candidates")

    path = artifact_path(cwd, "candidate_papers.json")
    write_json(path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="literature",
        role="Literature Review Agent",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.artifacts.outline_json or ""],
        output_artifacts=[str(path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.artifacts.candidate_papers_json = str(path)
    state.current_phase = "literature_review"
    state.active_artifact = "candidate_papers.json"
    state.latest_discovery_mode = mode
    state.notes.append(f"Candidate papers discovered via {mode} mode.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    return path

