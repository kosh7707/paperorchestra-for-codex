from __future__ import annotations

from pathlib import Path

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json, write_text
from paperorchestra.core.models import VerifiedPaper
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.research_candidate_verification import (
    CandidateVerificationFailure,
    verify_candidate_registry,
)
from paperorchestra.engine.research_registry_io import load_prior_citation_registry
from paperorchestra.engine.research_registry_merge import (
    merge_live_verified_with_prior_registry as _merge_live_verified_with_prior_registry,
)
from paperorchestra.engine.research_registry_payloads import citation_map_from_registry as _citation_map_from_registry
from paperorchestra.engine.research_verification_errors import _record_verification_errors
from paperorchestra.research.bibtex import ensure_unique_bibtex_keys, registry_to_bibtex
from paperorchestra.research.literature import serialize_registry, verify_candidate_title


def build_bib(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if not state.artifacts.citation_registry_json:
        raise ContractError("Run verify-papers before build-bib.")
    registry = [VerifiedPaper(**item) for item in read_json(state.artifacts.citation_registry_json)]
    bib = registry_to_bibtex(registry)
    path = artifact_path(cwd, "references.bib")
    write_text(path, bib)
    citation_map_path = artifact_path(cwd, "citation_map.json")
    citation_map = _citation_map_from_registry(registry)
    write_json(citation_map_path, citation_map)
    state.artifacts.references_bib = str(path)
    state.artifacts.citation_map_json = str(citation_map_path)
    state.active_artifact = "references.bib"
    state.notes.append("BibTeX file generated.")
    save_session(cwd, state)
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
    try:
        verified = verify_candidate_registry(
            candidates,
            cutoff_date=state.inputs.cutoff_date,
            mode=mode,
            min_ratio=min_ratio,
            on_error=on_error,
            live_verifier=verify_candidate_title,
        )
    except CandidateVerificationFailure as exc:
        error_path = _record_verification_errors(
            cwd,
            state,
            exc.errors,
            mode=mode,
            on_error=on_error,
        )
        state.current_phase = "blocked"
        state.active_artifact = Path(error_path).name if error_path else "verification_errors.json"
        save_session(cwd, state)
        raise ContractError(
            f"Live verification failed for candidate {exc.title!r}: {exc.original}. "
            "Set SEMANTIC_SCHOLAR_API_KEY, retry with --on-error skip, or use --verify-mode mock for offline demos."
        ) from exc.original

    registry = verified.registry
    verification_errors = verified.errors
    candidate_count = verified.candidate_count

    prior_registry = load_prior_citation_registry(
        state,
        note_prefix="Existing citation registry could not be loaded",
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
