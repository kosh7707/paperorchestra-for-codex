from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.engine.completion_identity import _lane_owner
from paperorchestra.runtime.parity import record_lane_manifest

REFINEMENT_STAGE = "refinement"
REFINEMENT_ROLE = "Content Refinement Agent"


def refinement_lane_manifest_kwargs(
    *,
    runtime_mode: str,
    lane_type: str,
    owner: str,
    fallback_used: bool,
    accepted: bool,
    compile_blocked: bool,
    input_artifacts: list[str],
    output_artifacts: list[str],
    notes: list[str],
) -> dict[str, Any]:
    if accepted:
        status = "fallback_completed" if fallback_used else "completed"
    else:
        status = "blocked" if compile_blocked else "failed"
    return {
        "stage": REFINEMENT_STAGE,
        "role": REFINEMENT_ROLE,
        "runtime_mode": runtime_mode,
        "lane_type": lane_type,
        "owner": owner,
        "status": status,
        "input_artifacts": input_artifacts,
        "output_artifacts": output_artifacts,
        "fallback_used": fallback_used,
        "notes": notes,
    }


def record_accepted_refinement_lane_manifest(
    cwd: str | Path | None,
    *,
    runtime_mode: str,
    lane_type: str,
    fallback_used: bool,
    input_artifacts: list[str],
    output_artifacts: list[str],
    notes: list[str],
) -> Path:
    return record_lane_manifest(
        cwd,
        **refinement_lane_manifest_kwargs(
            runtime_mode=runtime_mode,
            lane_type=lane_type,
            owner=_lane_owner(lane_type, fallback_used),
            fallback_used=fallback_used,
            accepted=True,
            compile_blocked=False,
            input_artifacts=input_artifacts,
            output_artifacts=output_artifacts,
            notes=notes,
        ),
    )


def record_rejected_refinement_lane_manifest(
    cwd: str | Path | None,
    *,
    runtime_mode: str,
    lane_type: str,
    fallback_used: bool,
    compile_error: str | None,
    input_artifacts: list[str],
    output_artifacts: list[str],
    notes: list[str],
) -> Path:
    return record_lane_manifest(
        cwd,
        **refinement_lane_manifest_kwargs(
            runtime_mode=runtime_mode,
            lane_type=lane_type,
            owner=_lane_owner(lane_type, fallback_used),
            fallback_used=fallback_used,
            accepted=False,
            compile_blocked=bool(compile_error),
            input_artifacts=input_artifacts,
            output_artifacts=output_artifacts,
            notes=notes,
        ),
    )
