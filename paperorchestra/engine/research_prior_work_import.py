from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from paperorchestra.core.errors import ContractError


def import_prior_work_with_hooks(
    cwd: str | Path | None,
    *,
    seed_file: str | Path,
    source: str,
    require_complete_metadata: bool,
    load_session_fn: Callable[..., Any],
    save_session_fn: Callable[..., Any],
    load_prior_work_seed_fn: Callable[..., list[dict[str, Any]]],
    entries_to_registry_fn: Callable[..., list[Any]],
    load_prior_registry_fn: Callable[..., list[Any]],
    merge_registries_fn: Callable[[list[Any], list[Any]], list[Any]],
    filter_entries_fn: Callable[[list[dict[str, Any]]], tuple[list[dict[str, Any]], list[dict[str, Any]]]],
    write_rejection_report_fn: Callable[..., Path],
    write_artifacts_fn: Callable[..., dict[str, Path]],
    record_lane_manifest_fn: Callable[..., Path],
) -> dict[str, str]:
    state = load_session_fn(cwd)
    entries = load_prior_work_seed_fn(seed_file, source=source)
    rejection_report_path = None
    if require_complete_metadata:
        original_count = len(entries)
        entries, rejected_entries = filter_entries_fn(entries)
        rejection_report_path = write_rejection_report_fn(
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
    registry = entries_to_registry_fn(entries, cutoff_date=state.inputs.cutoff_date)
    if not registry:
        if require_complete_metadata and rejection_report_path is not None:
            save_session_fn(cwd, state)
            raise ContractError(
                f"No complete prior-work entries were imported from {seed_file}. "
                f"Rejected entries are recorded in {rejection_report_path}."
            )
        raise ContractError(f"No usable prior-work entries were imported from {seed_file}.")

    prior_registry = load_prior_registry_fn(
        state,
        note_prefix="Existing citation registry could not be loaded during prior-work import",
    )
    if prior_registry:
        imported_count = len(registry)
        registry = merge_registries_fn(prior_registry, registry)
        state.notes.append(
            "Prior-work import merged with and preserved the existing citation registry "
            f"({len(prior_registry)} existing, {imported_count} imported, {len(registry)} total)."
        )

    artifact_paths = write_artifacts_fn(cwd, registry, source=source)
    candidate_path = artifact_paths["candidate_papers_json"]
    registry_path = artifact_paths["citation_registry_json"]
    citation_map_path = artifact_paths["citation_map_json"]
    references_path = artifact_paths["references_bib"]

    lane_path = record_lane_manifest_fn(
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
    save_session_fn(cwd, state)

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


__all__ = ["import_prior_work_with_hooks"]
