from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.manuscript.citations import canonical_citation_key, extract_citation_keys
from paperorchestra.reviews.reproducibility_artifacts import (
    _read_json_if_exists,
    _read_json_payload_if_exists,
)
from paperorchestra.reviews import reproducibility_payloads as _payloads


def _bibtex_keys_from_text(text: str) -> set[str]:
    return set(re.findall(r"(?m)^\s*@[A-Za-z]+\s*\{\s*([^,\s]+)", text))


def _citation_keys_from_latex(path: str | Path | None) -> set[str]:
    if not path:
        return set()
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return set()
    return extract_citation_keys(candidate.read_text(encoding="utf-8", errors="replace"))


def _citation_support_review_provenance(cwd: str | Path | None, state, session_artifact_dir: Path | None) -> dict[str, Any]:
    candidates: list[Path] = [artifact_path(cwd, "citation_support_review.json")]
    if session_artifact_dir is not None:
        candidates.append(session_artifact_dir / "citation_support_review.json")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        payload = _read_json_if_exists(candidate)
        if not isinstance(payload, dict):
            continue
        provenance = payload.get("evidence_provenance") if isinstance(payload.get("evidence_provenance"), dict) else {}
        mode = str(payload.get("review_mode") or provenance.get("mode") or "")
        provider_name = provenance.get("provider_name")
        model_review_used = bool(provenance.get("model_review_used"))
        live = mode in {"model", "web"} and model_review_used and provider_name != "mock"
        return {
            "status": "present",
            "path": str(candidate),
            "mode": mode,
            "provider_name": provider_name,
            "web_search_required": bool(provenance.get("web_search_required")),
            "model_review_used": model_review_used,
            "semantic_scholar_required": bool(provenance.get("semantic_scholar_required")),
            "live": live,
        }
    return {"status": "missing", "path": str(candidates[0]), "live": False, "semantic_scholar_required": False}


def _registry_surface_health(registry_exists: bool, registry_payload: Any) -> tuple[list[str], int, set[str], set[str]]:
    if not registry_exists:
        return [], 0, set(), set()
    if not isinstance(registry_payload, list):
        return ["citation_registry.json is unreadable or malformed."], 0, set(), set()

    invalid = 0
    registry_keys: set[str] = set()
    registry_alias_keys: set[str] = set()
    for item in registry_payload:
        if not _payloads._is_valid_verified_paper_payload(item):
            invalid += 1
            continue
        key = item.get("bibtex_key")
        aliases = item.get("alias_bibtex_keys") or []
        if isinstance(key, str) and key.strip():
            registry_keys.add(key.strip())
        registry_alias_keys.update(alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip())
    valid = len(registry_payload) - invalid
    if valid == 0 and invalid == 0:
        return ["citation_registry.json is empty."], 0, registry_keys, registry_alias_keys
    if invalid > 0:
        return [f"citation_registry.json contains malformed entries ({invalid} invalid)."], valid, registry_keys, registry_alias_keys
    return [], valid, registry_keys, registry_alias_keys


def _citation_map_surface_health(citation_map_exists: bool, citation_map_payload: Any) -> tuple[list[str], int, set[str], set[str]]:
    if not citation_map_exists:
        return [], 0, set(), set()
    if not isinstance(citation_map_payload, dict):
        return ["citation_map.json is unreadable or malformed."], 0, set(), set()

    invalid = 0
    citation_map_keys: set[str] = set()
    citation_map_canonical_keys: set[str] = set()
    for key, entry in citation_map_payload.items():
        if not _payloads._is_valid_citation_map_entry(key, entry):
            invalid += 1
            continue
        citation_map_keys.add(key.strip())
        citation_map_canonical_keys.add(canonical_citation_key(key.strip(), citation_map_payload))
    valid = len(citation_map_payload) - invalid
    if valid == 0 and invalid == 0:
        return ["citation_map.json is empty."], 0, citation_map_keys, citation_map_canonical_keys
    if invalid > 0:
        return [f"citation_map.json contains malformed entries ({invalid} invalid)."], valid, citation_map_keys, citation_map_canonical_keys
    return [], valid, citation_map_keys, citation_map_canonical_keys


def _references_bib_surface_health(references_bib_path: str | Path | None, references_bib_exists: bool) -> tuple[list[str], int, set[str]]:
    if not references_bib_exists:
        return [], 0, set()
    bib_candidate = Path(references_bib_path)
    if not bib_candidate.is_file():
        return ["references.bib is unreadable or malformed."], 0, set()
    try:
        bib_text = bib_candidate.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["references.bib is unreadable or malformed."], 0, set()

    entry_count = len(re.findall(r"(?m)^\s*@[A-Za-z]+(?:\s*|\{)", bib_text))
    bib_keys = _bibtex_keys_from_text(bib_text)
    if entry_count == 0:
        return ["references.bib is empty."], entry_count, bib_keys
    if not bib_keys:
        return ["references.bib contains BibTeX entries without extractable keys."], entry_count, bib_keys
    return [], entry_count, bib_keys


def _append_cross_artifact_issues(
    issues: list[str],
    *,
    registry_keys: set[str],
    registry_alias_keys: set[str],
    citation_map_keys: set[str],
    bib_keys: set[str],
    manuscript_citation_keys: set[str],
) -> None:
    if registry_keys and citation_map_keys:
        missing_from_map = sorted((registry_keys | registry_alias_keys) - citation_map_keys)
        allowed_map_keys = registry_keys | registry_alias_keys
        extra_in_map = sorted(citation_map_keys - allowed_map_keys)
        if missing_from_map:
            issues.append("citation_map.json is missing registry key(s): " + ", ".join(missing_from_map[:10]))
        if extra_in_map:
            issues.append("citation_map.json contains key(s) not present in citation_registry.json: " + ", ".join(extra_in_map[:10]))
    if registry_keys and bib_keys:
        missing_from_bib = sorted(registry_keys - bib_keys)
        extra_in_bib = sorted(bib_keys - registry_keys)
        if missing_from_bib:
            issues.append("references.bib is missing registry key(s): " + ", ".join(missing_from_bib[:10]))
        if extra_in_bib:
            issues.append("references.bib contains key(s) not present in citation_registry.json: " + ", ".join(extra_in_bib[:10]))
    if manuscript_citation_keys:
        if citation_map_keys:
            missing_from_map = sorted(manuscript_citation_keys - citation_map_keys)
            if missing_from_map:
                issues.append("manuscript cites key(s) missing from citation_map.json: " + ", ".join(missing_from_map[:10]))
        if bib_keys:
            missing_from_bib = sorted(manuscript_citation_keys - bib_keys)
            if missing_from_bib:
                issues.append("manuscript cites key(s) missing from references.bib: " + ", ".join(missing_from_bib[:10]))


def _citation_surface_health(state) -> dict[str, Any]:
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
