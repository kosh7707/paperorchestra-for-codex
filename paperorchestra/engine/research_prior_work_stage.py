from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
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


def import_prior_work(
    cwd: str | Path | None,
    *,
    seed_file: str | Path,
    source: str = "manual_seed",
    require_complete_metadata: bool = False,
) -> dict[str, str]:
    state = load_session(cwd)
    entries = load_prior_work_seed(seed_file, source=source)
    rejection_report_path: Path | None = None
    if require_complete_metadata:
        original_count = len(entries)
        entries, rejected_entries = _filter_prior_work_entries_for_complete_metadata(entries)
        rejection_report_path = _write_prior_work_import_rejection_report(
            cwd,
            seed_file=seed_file,
            source=source,
            original_count=original_count,
            kept_count=len(entries),
            rejected=rejected_entries,
            require_complete_metadata=require_complete_metadata,
        )
        if rejected_entries:
            state.notes.append(
                f"Rejected {len(rejected_entries)} prior-work seed entr(y/ies) with incomplete rendered-reference metadata. "
                f"Report: {rejection_report_path.name}."
            )
    registry = prior_work_entries_to_verified_papers(entries, cutoff_date=state.inputs.cutoff_date)
    if not registry:
        if require_complete_metadata and rejection_report_path is not None:
            save_session(cwd, state)
            raise ContractError(
                f"No complete prior-work entries were imported from {seed_file}. "
                f"Rejected entries are recorded in {rejection_report_path}."
            )
        raise ContractError(f"No usable prior-work entries were imported from {seed_file}.")
    prior_registry = load_prior_citation_registry(
        state,
        note_prefix="Existing citation registry could not be loaded during prior-work import",
    )
    if prior_registry:
        imported_count = len(registry)
        registry = _merge_live_verified_with_prior_registry(prior_registry, registry)
        state.notes.append(
            "Prior-work import merged with and preserved the existing citation registry "
            f"({len(prior_registry)} existing, {imported_count} imported, {len(registry)} total)."
        )

    artifact_paths = write_prior_work_import_artifacts(cwd, registry, source=source)
    candidate_path = artifact_paths["candidate_papers_json"]
    registry_path = artifact_paths["citation_registry_json"]
    citation_map_path = artifact_paths["citation_map_json"]
    references_path = artifact_paths["references_bib"]

    lane_path = record_lane_manifest(
        cwd,
        stage="literature",
        role="Curated Prior Work Import",
        runtime_mode="curated_seed",
        lane_type="manual",
        owner="operator",
        status="completed",
        input_artifacts=[str(seed_file)],
        output_artifacts=[str(candidate_path), str(registry_path), str(citation_map_path), str(references_path)],
        fallback_used=False,
        notes=[
            f"Imported {len(registry)} curated prior-work entries from {seed_file}.",
            "Entries are curated seed metadata, not live Semantic Scholar verification unless the source says so.",
        ],
    )
    state.artifacts.candidate_papers_json = str(candidate_path)
    state.artifacts.citation_registry_json = str(registry_path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.artifacts.references_bib = str(references_path)
    state.current_phase = "literature_review"
    state.active_artifact = "references.bib"
    state.latest_discovery_mode = source
    state.notes.append(f"Imported curated prior work from {seed_file}.")
    state.notes.append(f"Lane manifest recorded: {lane_path.name}")
    save_session(cwd, state)
    result = {
        "candidate_papers_json": str(candidate_path),
        "citation_registry_json": str(registry_path),
        "citation_map_json": str(citation_map_path),
        "references_bib": str(references_path),
        "lane_manifest": str(lane_path),
    }
    if rejection_report_path is not None:
        result["rejection_report_json"] = str(rejection_report_path)
    return result
