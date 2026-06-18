from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable

from paperorchestra.core.errors import ContractError
from paperorchestra.core.session import load_session as _load_session, save_session as _save_session
from paperorchestra.engine.prior_work_policy import (
    _filter_prior_work_entries_for_complete_metadata as _filter_prior_work_entries_for_complete_metadata_real,
    _write_prior_work_import_rejection_report as _write_prior_work_import_rejection_report_real,
)
from paperorchestra.engine.research_prior_work_artifacts import write_prior_work_import_artifacts as _write_prior_work_import_artifacts_real
from paperorchestra.engine.research_registry_io import load_prior_citation_registry as _load_prior_citation_registry_real
from paperorchestra.engine.research_registry_merge import merge_live_verified_with_prior_registry as _merge_live_verified_with_prior_registry_real
from paperorchestra.research.prior_work_seed import (
    load_prior_work_seed as _load_prior_work_seed_real,
    prior_work_entries_to_verified_papers as _prior_work_entries_to_verified_papers_real,
)
from paperorchestra.runtime.parity import record_lane_manifest as _record_lane_manifest_real


def _stage_dependency(name: str, default: Callable[..., Any]) -> Callable[..., Any]:
    stage = sys.modules.get("paperorchestra.engine.research_prior_work_stage")
    if stage is None:
        return default
    return getattr(stage, name, default)


def import_prior_work(
    cwd: str | Path | None,
    *,
    seed_file: str | Path,
    source: str = "manual_seed",
    require_complete_metadata: bool = False,
) -> dict[str, str]:
    state = _stage_dependency("load_session", _load_session)(cwd)
    entries = _stage_dependency("load_prior_work_seed", _load_prior_work_seed_real)(seed_file, source=source)
    rejection_report_path: Path | None = None
    if require_complete_metadata:
        original_count = len(entries)
        entries, rejected_entries = _stage_dependency(
            "_filter_prior_work_entries_for_complete_metadata",
            _filter_prior_work_entries_for_complete_metadata_real,
        )(entries)
        rejection_report_path = _stage_dependency(
            "_write_prior_work_import_rejection_report",
            _write_prior_work_import_rejection_report_real,
        )(
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
    registry = _stage_dependency(
        "prior_work_entries_to_verified_papers",
        _prior_work_entries_to_verified_papers_real,
    )(entries, cutoff_date=state.inputs.cutoff_date)
    if not registry:
        if require_complete_metadata and rejection_report_path is not None:
            _stage_dependency("save_session", _save_session)(cwd, state)
            raise ContractError(
                f"No complete prior-work entries were imported from {seed_file}. "
                f"Rejected entries are recorded in {rejection_report_path}."
            )
        raise ContractError(f"No usable prior-work entries were imported from {seed_file}.")
    prior_registry = _stage_dependency("load_prior_citation_registry", _load_prior_citation_registry_real)(
        state,
        note_prefix="Existing citation registry could not be loaded during prior-work import",
    )
    if prior_registry:
        imported_count = len(registry)
        registry = _stage_dependency(
            "_merge_live_verified_with_prior_registry",
            _merge_live_verified_with_prior_registry_real,
        )(prior_registry, registry)
        state.notes.append(
            "Prior-work import merged with and preserved the existing citation registry "
            f"({len(prior_registry)} existing, {imported_count} imported, {len(registry)} total)."
        )

    artifact_paths = _stage_dependency(
        "write_prior_work_import_artifacts",
        _write_prior_work_import_artifacts_real,
    )(cwd, registry, source=source)
    candidate_path = artifact_paths["candidate_papers_json"]
    registry_path = artifact_paths["citation_registry_json"]
    citation_map_path = artifact_paths["citation_map_json"]
    references_path = artifact_paths["references_bib"]

    lane_path = _stage_dependency("record_lane_manifest", _record_lane_manifest_real)(
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
    _stage_dependency("save_session", _save_session)(cwd, state)
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
