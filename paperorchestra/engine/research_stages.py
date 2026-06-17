from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import extract_json, read_json, read_text, write_json, write_text
from paperorchestra.core.models import VerifiedPaper
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.completion import _build_completion_request, _complete_with_runtime_mode, _lane_owner
from paperorchestra.engine.prompt_context import _data_block, _prompt_compact_text, _read_inputs
from paperorchestra.engine.research_discovery import _build_candidate_payload
from paperorchestra.engine.research_registry import (
    _citation_map_from_registry,
    _merge_live_verified_with_prior_registry,
)
from paperorchestra.engine.schemas import PRIOR_WORK_SEED_SCHEMA
from paperorchestra.research.literature import (
    ensure_unique_bibtex_keys,
    load_prior_work_seed,
    mock_verified_paper,
    prior_work_entries_to_verified_papers,
    registry_to_bibtex,
    serialize_registry,
    verify_candidate_title,
)
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


def _record_verification_errors(
    cwd: str | Path | None,
    state,
    errors: list[dict[str, Any]],
    *,
    mode: str,
    on_error: str,
) -> Path | None:
    if not errors:
        return None
    path = artifact_path(cwd, "verification_errors.json")
    write_json(
        path,
        {
            "mode": mode,
            "on_error": on_error,
            "error_count": len(errors),
            "errors": errors,
            "recovery_hints": [
                "Set SEMANTIC_SCHOLAR_API_KEY for more reliable live verification.",
                "Retry `paperorchestra run --provider shell --discovery-mode search-grounded` to keep any candidates that verify successfully.",
                "Use `paperorchestra run --provider mock` only for demos or offline dry runs.",
            ],
        },
    )
    state.artifacts.latest_verification_errors_json = str(path)
    state.notes.append(f"Recorded {len(errors)} live verification error(s): {path.name}")
    return path


def verify_papers(
    cwd: str | Path | None,
    *,
    min_ratio: float = 70.0,
    mode: str = "live",
    on_error: str = "skip",
) -> Path:
    if on_error not in {"skip", "fail"}:
        raise ContractError(f"Unsupported verification error policy: {on_error}")
    state = load_session(cwd)
    if not state.artifacts.candidate_papers_json:
        raise ContractError("Run discover-papers before verify-papers.")
    candidates = read_json(state.artifacts.candidate_papers_json)
    registry: list[VerifiedPaper] = []
    seen_ids: set[str] = set()
    verification_errors: list[dict[str, Any]] = []
    candidate_count = 0
    for bucket in ["macro_candidates", "micro_candidates"]:
        for candidate in candidates.get(bucket, []):
            title = candidate.get("title_guess")
            if not title:
                continue
            candidate_count += 1
            if mode == "mock":
                paper = mock_verified_paper(
                    title,
                    abstract_hint=candidate.get("why_relevant", ""),
                    cutoff_date=state.inputs.cutoff_date,
                    origin=bucket,
                    query_hint=candidate.get("origin_query") or title,
                )
            elif mode == "live":
                try:
                    paper = verify_candidate_title(
                        title,
                        cutoff_date=state.inputs.cutoff_date,
                        query_hint=candidate.get("origin_query") or title,
                        min_ratio=min_ratio,
                    )
                except Exception as exc:
                    error = {
                        "bucket": bucket,
                        "title_guess": title,
                        "query_hint": candidate.get("origin_query") or title,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "action": "failed" if on_error == "fail" else "skipped",
                    }
                    verification_errors.append(error)
                    if on_error == "fail":
                        error_path = _record_verification_errors(
                            cwd,
                            state,
                            verification_errors,
                            mode=mode,
                            on_error=on_error,
                        )
                        state.current_phase = "blocked"
                        state.active_artifact = Path(error_path).name if error_path else "verification_errors.json"
                        save_session(cwd, state)
                        raise ContractError(
                            f"Live verification failed for candidate {title!r}: {exc}. "
                            "Set SEMANTIC_SCHOLAR_API_KEY, retry with --on-error skip, or use --verify-mode mock for offline demos."
                        ) from exc
                    continue
            else:
                raise ContractError(f"Unsupported verify mode: {mode}")
            if not paper or paper.is_after_cutoff or paper.paper_id in seen_ids:
                continue
            paper.origin = bucket
            registry.append(paper)
            seen_ids.add(paper.paper_id)

    prior_registry: list[VerifiedPaper] = []
    if state.artifacts.citation_registry_json and Path(state.artifacts.citation_registry_json).exists():
        try:
            prior_payload = read_json(state.artifacts.citation_registry_json)
            if isinstance(prior_payload, list):
                prior_registry = [VerifiedPaper(**item) for item in prior_payload if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            prior_registry = []
            state.notes.append(
                "Existing citation registry could not be loaded and was treated as empty: "
                f"{exc.__class__.__name__}."
            )

    verified_registry_count = len(registry)
    registry = _merge_live_verified_with_prior_registry(prior_registry, registry)
    if prior_registry and len(registry) >= len(prior_registry):
        state.notes.append(
            "Live verification merged with and preserved the prior registry artifacts "
            f"({verified_registry_count} live verified, {len(prior_registry)} prior curated, {len(registry)} total)."
        )

    preserve_prior_registry = (
        mode == "live"
        and on_error == "skip"
        and bool(verification_errors)
        and bool(prior_registry)
        and len(registry) < len(prior_registry)
    )

    if preserve_prior_registry:
        registry = prior_registry
        state.notes.append(
            "Live verification returned fewer verified papers than the existing registry after candidate-level errors; preserved the prior registry artifacts."
        )

    ensure_unique_bibtex_keys(registry)

    path = artifact_path(cwd, "citation_registry.json")
    serialize_registry(path, registry)
    citation_map = _citation_map_from_registry(registry)
    citation_map_path = artifact_path(cwd, "citation_map.json")
    write_json(citation_map_path, citation_map)

    verification_errors_path = _record_verification_errors(
        cwd,
        state,
        verification_errors,
        mode=mode,
        on_error=on_error,
    )
    state.latest_verify_mode = mode
    if mode != "live":
        state.latest_verify_fallback_used = None
    if mode == "live" and candidate_count > 0 and verification_errors and not registry:
        state.current_phase = "blocked"
        state.active_artifact = Path(verification_errors_path).name if verification_errors_path else "verification_errors.json"
        save_session(cwd, state)
        raise ContractError(
            "Live verification produced no verified papers after candidate-level errors. "
            "Set SEMANTIC_SCHOLAR_API_KEY, reduce request volume and retry, or rerun with --verify-mode mock for offline demos. "
            f"Details: {verification_errors_path}"
        )
    state.artifacts.citation_registry_json = str(path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.active_artifact = "citation_registry.json"
    if verification_errors:
        state.notes.append(
            f"Skipped {len(verification_errors)} candidate verification error(s) while verifying {len(registry)} paper(s)."
        )
    state.notes.append(f"Verified {len(registry)} papers via {mode} mode.")
    save_session(cwd, state)
    return path


def build_bib(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if not state.artifacts.citation_registry_json:
        raise ContractError("Run verify-papers before build-bib.")
    registry = [VerifiedPaper(**item) for item in read_json(state.artifacts.citation_registry_json)]
    bib = registry_to_bibtex(registry)
    path = artifact_path(cwd, "references.bib")
    write_text(path, bib)
    citation_map_path = artifact_path(cwd, "citation_map.json")
    write_json(citation_map_path, _citation_map_from_registry(registry))
    state.artifacts.references_bib = str(path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.active_artifact = "references.bib"
    state.notes.append("BibTeX file generated.")
    save_session(cwd, state)
    return path


def _prior_work_context_from_paths(paper: str | Path | None, artifact_repo: str | Path | None) -> str:
    chunks: list[str] = []
    if paper:
        paper_path = Path(paper).resolve()
        if paper_path.exists():
            chunks.append(_data_block("source_paper.tex", read_text(paper_path)))
            references = paper_path.parent / "references.bib"
            if references.exists():
                chunks.append(_data_block("source_references.bib", read_text(references)))
    if artifact_repo:
        repo = Path(artifact_repo).resolve()
        for rel in ["README.md", "benchmarks/result.txt", "benchmarks/DATA_FORMAT.md"]:
            path = repo / rel
            if path.exists():
                chunks.append(_data_block(f"artifact_repo/{rel}", read_text(path)))
    return "\n\n".join(chunks) if chunks else ""


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
    extra_context = _prompt_compact_text(_prior_work_context_from_paths(paper, artifact_repo), head_chars=6000, tail_chars=1000)
    prompt_idea = _prompt_compact_text(inputs["idea"], head_chars=6000, tail_chars=1000)
    prompt_experimental_log = _prompt_compact_text(inputs["experimental_log"], head_chars=10000, tail_chars=2000)
    user_prompt = f"""
{_data_block('idea.md', prompt_idea)}

{_data_block('experimental_log.md', prompt_experimental_log)}

{_data_block('conference_guidelines.md', inputs['guidelines'])}

{_data_block('cutoff_date', state.inputs.cutoff_date or 'null')}

{extra_context}

Task:
Produce a curated prior_work seed JSON for this research paper. Prefer canonical standards, foundational papers, benchmark/spec documents, and close prior work. If this runtime has web/search tools, use them conservatively; otherwise derive only from supplied materials. Do not invent authors or venues. If uncertain, include a provenance note saying what must be manually verified.

Return JSON with exactly two top-level keys: references and research_notes.
""".strip()
    system_prompt = f"""
You are a prior-work seed generator for PaperOrchestra.
Return one valid JSON object matching this contract:
- references: array of objects with title, authors, year, venue, url, doi, source, why_relevant, provenance_notes
- research_notes: array of concise caveats or follow-up checks

Rules:
- Use source={source!r} unless an entry has a more precise provenance.
- Prefer official RFC/NIST/spec URLs for standards.
- Do not fabricate bibliographic metadata. Use null for unknown year/venue/url/doi.
- This seed is an input to import-prior-work; it is not live Semantic Scholar verification.

""".strip()
    response, lane_type, fallback_used, lane_notes = _complete_with_runtime_mode(
        _build_completion_request(system_prompt=system_prompt, user_prompt=user_prompt),
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
    current_session_id = state.session_id
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


def _prior_work_metadata_rejection_reasons(entry: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    unknown_values = {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}

    def is_unknown(value: Any) -> bool:
        normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
        return normalized in unknown_values

    if is_unknown(entry.get("title")):
        reasons.append("missing_title")
    authors = [author for author in entry.get("authors", []) if not is_unknown(author)]
    if not authors:
        reasons.append("missing_author_or_organization")
    if not isinstance(entry.get("year"), int):
        reasons.append("missing_year")
    elif entry.get("year_source") not in {"year", "publication_year"}:
        reasons.append("missing_explicit_year")
    return reasons


def _filter_prior_work_entries_for_complete_metadata(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        reasons = _prior_work_metadata_rejection_reasons(entry)
        if not reasons:
            kept.append(entry)
            continue
        rejected.append(
            {
                "index": index,
                "title": str(entry.get("title") or "").strip() or None,
                "source": str(entry.get("source") or "").strip() or None,
                "reasons": reasons,
                "has_publication_date": bool(str(entry.get("publication_date") or "").strip()),
            }
        )
    return kept, rejected


def _write_prior_work_import_rejection_report(
    cwd: str | Path | None,
    *,
    seed_file: str | Path,
    source: str,
    original_count: int,
    kept_count: int,
    rejected: list[dict[str, Any]],
    require_complete_metadata: bool,
) -> Path:
    path = artifact_path(cwd, "prior_work_import_rejections.json")
    reason_counts: dict[str, int] = {}
    for item in rejected:
        for reason in item.get("reasons", []):
            if isinstance(reason, str):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
    write_json(
        path,
        {
            "schema_version": "prior-work-import-rejections/1",
            "seed_file": str(seed_file),
            "source": source,
            "require_complete_metadata": require_complete_metadata,
            "policy": {
                "required_fields": ["title", "author_or_organization", "year"],
                "all_rejected_behavior": "fail_import_and_leave_existing_registry_unchanged",
                "publication_date_without_year": "rejected_until_a_concrete_year_is_provided",
            },
            "input_entry_count": original_count,
            "accepted_entry_count": kept_count,
            "rejected_entry_count": len(rejected),
            "reason_counts": reason_counts,
            "rejected_entries": rejected,
        },
    )
    return path


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
    prior_registry: list[VerifiedPaper] = []
    if state.artifacts.citation_registry_json and Path(state.artifacts.citation_registry_json).exists():
        try:
            prior_payload = read_json(state.artifacts.citation_registry_json)
            if isinstance(prior_payload, list):
                prior_registry = [VerifiedPaper(**item) for item in prior_payload if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            prior_registry = []
            state.notes.append(
                "Existing citation registry could not be loaded during prior-work import and was treated as empty: "
                f"{exc.__class__.__name__}."
            )
    if prior_registry:
        imported_count = len(registry)
        registry = _merge_live_verified_with_prior_registry(prior_registry, registry)
        state.notes.append(
            "Prior-work import merged with and preserved the existing citation registry "
            f"({len(prior_registry)} existing, {imported_count} imported, {len(registry)} total)."
        )

    candidate_payload = {
        "macro_candidates": [
            {
                "title_guess": paper.title,
                "why_relevant": paper.abstract,
                "origin_query": paper.matched_query or paper.title,
                "role_guess": "macro",
                "discovery_source": paper.origin or source,
                "discovery_sources": [paper.origin or source],
            }
            for paper in registry
        ],
        "micro_candidates": [],
    }
    candidate_path = artifact_path(cwd, "candidate_papers.json")
    registry_path = artifact_path(cwd, "citation_registry.json")
    citation_map_path = artifact_path(cwd, "citation_map.json")
    references_path = artifact_path(cwd, "references.bib")
    write_json(candidate_path, candidate_payload)
    serialize_registry(registry_path, registry)
    write_json(citation_map_path, _citation_map_from_registry(registry))
    write_text(references_path, registry_to_bibtex(registry))

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
