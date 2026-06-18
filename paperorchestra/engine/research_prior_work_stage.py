from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import extract_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode, _lane_owner
from paperorchestra.engine.prompt_context import _read_inputs
from paperorchestra.engine.prior_work_prompt import build_prior_work_seed_prompts
from paperorchestra.engine.prior_work_policy import (
    _filter_prior_work_entries_for_complete_metadata,
    _write_prior_work_import_rejection_report,
)
from paperorchestra.engine.research_prior_work_artifacts import write_prior_work_import_artifacts
from paperorchestra.engine.research_prior_work_import_stage import import_prior_work
from paperorchestra.engine.research_registry import _merge_live_verified_with_prior_registry
from paperorchestra.engine.research_registry_io import load_prior_citation_registry
from paperorchestra.engine.schemas import PRIOR_WORK_SEED_SCHEMA
from paperorchestra.research.prior_work_seed import load_prior_work_seed, prior_work_entries_to_verified_papers
from paperorchestra.runtime.parity import record_lane_manifest
from paperorchestra.runtime.provider_base import BaseProvider


def research_prior_work(
    cwd: str | Path | None,
    provider: BaseProvider,
    *,
    output: str | Path | None = None,
    paper: str | Path | None = None,
    artifact_repo: str | Path | None = None,
    runtime_mode: str = "compatibility",
    source: str = "codex_web_seed",
    import_seed: bool = False,
    require_complete_metadata: bool = False,
) -> dict[str, Any]:
    state = load_session(cwd)
    inputs = _read_inputs(state)
    prompts = build_prior_work_seed_prompts(
        inputs,
        cutoff_date=state.inputs.cutoff_date,
        source=source,
        paper=paper,
        artifact_repo=artifact_repo,
    )
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=prompts.system_prompt, user_prompt=prompts.user_prompt),
        provider=provider,
        runtime_mode=runtime_mode,
        cwd=cwd,
        omx_lane_type="researcher",
        trace_stage="prior_work_seed",
        output_schema=PRIOR_WORK_SEED_SCHEMA,
    )
    payload = extract_json(response)
    for entry in payload.get("references", []):
        if isinstance(entry, dict):
            entry.setdefault("source", source)
    output_path = Path(output).resolve() if output else artifact_path(cwd, "prior_work_seed.json")
    write_json(output_path, payload)
    lane_path = record_lane_manifest(
        cwd,
        stage="prior_work_research",
        role="Prior Work Researcher",
        runtime_mode=runtime_mode,
        lane_type=lane_type,
        owner=_lane_owner(lane_type, fallback_used),
        status="fallback_completed" if fallback_used else "completed",
        input_artifacts=[state.inputs.idea_path, state.inputs.experimental_log_path],
        output_artifacts=[str(output_path)],
        fallback_used=fallback_used,
        notes=lane_notes,
    )
    state.notes.append(f"Prior-work seed generated: {output_path}")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    result: dict[str, Any] = {"path": str(output_path), "reference_count": len(payload.get("references", [])), "lane_manifest": str(lane_path)}
    if import_seed:
        result["imported"] = import_prior_work(
            cwd,
            seed_file=output_path,
            source=source,
            require_complete_metadata=require_complete_metadata,
        )
    return result
