from __future__ import annotations

from pathlib import Path

from paperorchestra.manuscript.citations import extract_citation_keys
from paperorchestra.reviews.reproducibility_artifacts import _read_json_payload_if_exists
from paperorchestra.reviews.reproducibility_citation_artifact_health import (
    _bibtex_keys_from_text,
    _citation_map_surface_health,
    _references_bib_surface_health,
    _registry_surface_health,
)
from paperorchestra.reviews.reproducibility_citation_crosscheck import _append_cross_artifact_issues


def _citation_keys_from_latex(path: str | Path | None) -> set[str]:
    if not path:
        return set()
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return set()
    return extract_citation_keys(candidate.read_text(encoding="utf-8", errors="replace"))


def _citation_surface_health(state) -> dict[str, object]:
    registry_path = state.artifacts.citation_registry_json
    citation_map_path = state.artifacts.citation_map_json
    references_bib_path = state.artifacts.references_bib

    registry_payload = _read_json_payload_if_exists(registry_path)
    citation_map_payload = _read_json_payload_if_exists(citation_map_path)
    registry_exists = bool(registry_path and Path(registry_path).exists())
    citation_map_exists = bool(citation_map_path and Path(citation_map_path).exists())
    references_bib_exists = bool(references_bib_path and Path(references_bib_path).exists())
    manuscript_citation_keys = _citation_keys_from_latex(state.artifacts.paper_full_tex)

    issues: list[str] = []
    citation_expected = bool(
        state.artifacts.paper_full_tex
        or state.artifacts.candidate_papers_json
        or state.latest_verify_mode
        or state.artifacts.references_bib
        or state.artifacts.citation_map_json
        or state.artifacts.citation_registry_json
    )
    if citation_expected and not registry_exists:
        issues.append("citation_registry.json is missing.")
    if citation_expected and not citation_map_exists:
        issues.append("citation_map.json is missing.")
    if citation_expected and not references_bib_exists:
        issues.append("references.bib is missing.")

    registry_issues, registry_count, registry_keys, registry_alias_keys = _registry_surface_health(registry_exists, registry_payload)
    map_issues, citation_map_count, citation_map_keys, citation_map_canonical_keys = _citation_map_surface_health(citation_map_exists, citation_map_payload)
    bib_issues, references_bib_entry_count, bib_keys = _references_bib_surface_health(references_bib_path, references_bib_exists)
    issues.extend(registry_issues)
    issues.extend(map_issues)
    issues.extend(bib_issues)
    _append_cross_artifact_issues(
        issues,
        registry_keys=registry_keys,
        registry_alias_keys=registry_alias_keys,
        citation_map_keys=citation_map_keys,
        bib_keys=bib_keys,
        manuscript_citation_keys=manuscript_citation_keys,
    )

    if not issues and registry_count and citation_map_count and references_bib_entry_count > 0 and registry_keys and citation_map_keys and bib_keys:
        status = "implemented"
    elif registry_exists or citation_map_exists or references_bib_exists or state.artifacts.candidate_papers_json:
        status = "partial"
    else:
        status = "missing"
    return {
        "status": status,
        "issues": issues,
        "registry_entry_count": registry_count,
        "citation_map_entry_count": citation_map_count,
        "references_bib_entry_count": references_bib_entry_count,
        "registry_keys": sorted(registry_keys),
        "registry_alias_keys": sorted(registry_alias_keys),
        "citation_map_keys": sorted(citation_map_keys),
        "citation_map_canonical_keys": sorted(citation_map_canonical_keys),
        "references_bib_keys": sorted(bib_keys),
        "manuscript_citation_keys": sorted(manuscript_citation_keys),
    }
