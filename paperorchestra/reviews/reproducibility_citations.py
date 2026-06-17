from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.core.session import artifact_path
from paperorchestra.manuscript.validator import canonical_citation_key, extract_citation_keys
from paperorchestra.reviews.reproducibility_artifacts import (
    _read_json_if_exists,
    _read_json_payload_if_exists,
)
from paperorchestra.reviews.reproducibility_payloads import (
    _is_external_id_value,
    _is_optional_int,
    _is_optional_real,
    _is_string_list,
    _is_valid_citation_map_entry,
    _is_valid_verified_paper_payload,
)


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


def _citation_surface_health(state) -> dict[str, Any]:
    registry_path = state.artifacts.citation_registry_json
    citation_map_path = state.artifacts.citation_map_json
    references_bib_path = state.artifacts.references_bib

    registry_payload = _read_json_payload_if_exists(registry_path)
    citation_map_payload = _read_json_payload_if_exists(citation_map_path)
    registry_exists = bool(registry_path and Path(registry_path).exists())
    citation_map_exists = bool(citation_map_path and Path(citation_map_path).exists())
    references_bib_exists = bool(references_bib_path and Path(references_bib_path).exists())

    registry_count = None
    citation_map_count = None
    references_bib_entry_count = 0
    registry_keys: set[str] = set()
    registry_alias_keys: set[str] = set()
    citation_map_keys: set[str] = set()
    citation_map_canonical_keys: set[str] = set()
    bib_keys: set[str] = set()
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

    if registry_exists:
        if not isinstance(registry_payload, list):
            issues.append("citation_registry.json is unreadable or malformed.")
        else:
            invalid_registry_entries = 0
            valid_registry_entries = 0
            for item in registry_payload:
                if _is_valid_verified_paper_payload(item):
                    valid_registry_entries += 1
                    key = item.get("bibtex_key")
                    aliases = item.get("alias_bibtex_keys") or []
                    if isinstance(key, str) and key.strip():
                        registry_keys.add(key.strip())
                    registry_alias_keys.update(alias.strip() for alias in aliases if isinstance(alias, str) and alias.strip())
                else:
                    invalid_registry_entries += 1
            registry_count = valid_registry_entries
            if valid_registry_entries == 0 and invalid_registry_entries == 0:
                issues.append("citation_registry.json is empty.")
            elif invalid_registry_entries > 0:
                issues.append(
                    f"citation_registry.json contains malformed entries ({invalid_registry_entries} invalid)."
                )
    if citation_map_exists:
        if not isinstance(citation_map_payload, dict):
            issues.append("citation_map.json is unreadable or malformed.")
        else:
            invalid_citation_map_entries = 0
            valid_citation_map_entries = 0
            for key, entry in citation_map_payload.items():
                if _is_valid_citation_map_entry(key, entry):
                    valid_citation_map_entries += 1
                    citation_map_keys.add(key.strip())
                    citation_map_canonical_keys.add(canonical_citation_key(key.strip(), citation_map_payload))
                else:
                    invalid_citation_map_entries += 1
            citation_map_count = valid_citation_map_entries
            if valid_citation_map_entries == 0 and invalid_citation_map_entries == 0:
                issues.append("citation_map.json is empty.")
            elif invalid_citation_map_entries > 0:
                issues.append(
                    f"citation_map.json contains malformed entries ({invalid_citation_map_entries} invalid)."
                )
    if references_bib_exists:
        bib_candidate = Path(references_bib_path)
        if not bib_candidate.is_file():
            issues.append("references.bib is unreadable or malformed.")
        else:
            try:
                bib_text = bib_candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                issues.append("references.bib is unreadable or malformed.")
            else:
                references_bib_entry_count = len(re.findall(r"(?m)^\s*@[A-Za-z]+(?:\s*|\{)", bib_text))
                bib_keys = _bibtex_keys_from_text(bib_text)
                if references_bib_entry_count == 0:
                    issues.append("references.bib is empty.")
                elif not bib_keys:
                    issues.append("references.bib contains BibTeX entries without extractable keys.")

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

    if not issues and registry_count and citation_map_count and references_bib_entry_count > 0 and registry_keys and citation_map_keys and bib_keys:
        status = "implemented"
    elif registry_exists or citation_map_exists or references_bib_exists or state.artifacts.candidate_papers_json:
        status = "partial"
    else:
        status = "missing"

    return {
        "status": status,
        "issues": issues,
        "registry_entry_count": registry_count or 0,
        "citation_map_entry_count": citation_map_count or 0,
        "references_bib_entry_count": references_bib_entry_count,
        "registry_keys": sorted(registry_keys),
        "registry_alias_keys": sorted(registry_alias_keys),
        "citation_map_keys": sorted(citation_map_keys),
        "citation_map_canonical_keys": sorted(citation_map_canonical_keys),
        "references_bib_keys": sorted(bib_keys),
        "manuscript_citation_keys": sorted(manuscript_citation_keys),
    }


def _mock_registry_entry_count(registry_path: str | Path | None) -> int:
    if not registry_path:
        return 0
    candidate = Path(registry_path)
    if not candidate.exists():
        return 0
    try:
        payload = read_json(candidate)
    except Exception:
        return 0
    count = 0
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            if _registry_entry_is_mock(item):
                count += 1
    return count


def _registry_entry_has_live_verification(item: dict[str, Any]) -> bool:
    """Return whether a citation-registry entry was actually live-verified.

    The registry's ``origin`` field can combine curated seed provenance and live
    discovery buckets, for example ``metadata_seed_for_live_verification`` after
    import and ``metadata_seed_for_live_verification+macro_candidates`` after a
    later Semantic Scholar match.  A bare seed label must not be counted as live
    evidence merely because it contains the word "live"; it is live only when a
    non-mock entry includes a real live verification bucket.
    """
    paper_id = str(item.get("paper_id") or "")
    if paper_id.startswith("mock-"):
        return False
    origin_tokens = {
        token.strip().lower()
        for token in re.split(r"[+,;]", str(item.get("origin") or ""))
        if token.strip()
    }
    live_buckets = {"macro_candidates", "micro_candidates"}
    return bool(origin_tokens & live_buckets)


def _registry_entry_is_mock(item: dict[str, Any]) -> bool:
    paper_id = str(item.get("paper_id") or "")
    authors = item.get("authors") or []
    venue = str(item.get("venue") or "")
    return paper_id.startswith("mock-") or authors == ["Mock Author"] or venue == "Mock Venue"


def _registry_entry_key_aliases(item: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("bibtex_key", "key"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            keys.add(value.strip())
    aliases = item.get("alias_bibtex_keys")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                keys.add(alias.strip())
    return keys


def _registry_entry_has_mixed_non_live_provenance(item: dict[str, Any]) -> bool:
    """Return whether a cited entry has usable non-live provenance.

    Seed entries imported specifically for later live verification are not
    enough to support a cited claim.  Separately supplied authoritative or
    manual sources can be useful, but they still need explicit mixed-provenance
    acceptance before a claim-safe run can be treated as ready.
    """

    origin_tokens = {
        token.strip().lower()
        for token in re.split(r"[+,;]", str(item.get("origin") or ""))
        if token.strip()
    }
    if origin_tokens and origin_tokens <= {"metadata_seed_for_live_verification"}:
        return False
    if origin_tokens & {"operator_authoritative_source", "manual_bibtex", "manual_seed", "codex_web_seed"}:
        return True
    external_ids = item.get("external_ids")
    has_external_ids = isinstance(external_ids, dict) and any(str(value).strip() for value in external_ids.values())
    has_url = bool(str(item.get("url") or "").strip())
    return has_url or has_external_ids


def _citation_registry_live_provenance(
    registry_path: str | Path | None,
    paper_path: str | Path | None = None,
) -> dict[str, Any]:
    empty_fields = {
        "registry_count": 0,
        "live_verified_count": 0,
        "seed_only_count": 0,
        "mock_entry_count": 0,
        "live_coverage_ratio": 0.0,
        "cited_entry_count": 0,
        "unused_registry_count": 0,
        "cited_live_verified_count": 0,
        "cited_mixed_count": 0,
        "cited_curated_seed_count": 0,
        "cited_mock_count": 0,
    }
    if not registry_path:
        return {**empty_fields, "status": "missing"}
    candidate = Path(registry_path)
    if not candidate.exists():
        return {**empty_fields, "status": "missing"}
    try:
        payload = read_json(candidate)
    except Exception:
        return {**empty_fields, "status": "unreadable"}
    if not isinstance(payload, list):
        return {**empty_fields, "status": "malformed"}
    entries = [item for item in payload if isinstance(item, dict)]
    registry_count = len(entries)
    live_verified_count = sum(1 for item in entries if _registry_entry_has_live_verification(item))
    mock_entry_count = sum(1 for item in entries if _registry_entry_is_mock(item))
    seed_only_count = max(registry_count - live_verified_count - mock_entry_count, 0)
    live_coverage_ratio = (live_verified_count / registry_count) if registry_count else 0.0
    cited_keys: set[str] | None = None
    if paper_path:
        paper = Path(paper_path)
        if paper.exists():
            cited_keys = extract_citation_keys(paper.read_text(encoding="utf-8", errors="replace"))
    if cited_keys is None:
        cited_entries = entries
    else:
        cited_entries = [item for item in entries if _registry_entry_key_aliases(item) & cited_keys]
    cited_entry_count = len(cited_entries)
    cited_live_verified_count = sum(1 for item in cited_entries if _registry_entry_has_live_verification(item))
    cited_mock_count = sum(1 for item in cited_entries if _registry_entry_is_mock(item))
    cited_mixed_count = sum(
        1
        for item in cited_entries
        if not _registry_entry_has_live_verification(item)
        and not _registry_entry_is_mock(item)
        and _registry_entry_has_mixed_non_live_provenance(item)
    )
    cited_curated_seed_count = max(
        cited_entry_count - cited_live_verified_count - cited_mock_count - cited_mixed_count,
        0,
    )
    unused_registry_count = max(registry_count - cited_entry_count, 0)
    cited_scope_active = cited_keys is not None
    if not registry_count:
        status = "empty"
    elif cited_mock_count:
        status = "mock"
    elif cited_mixed_count:
        status = "mixed"
    elif cited_curated_seed_count:
        status = "curated"
    elif cited_scope_active:
        status = "live"
    elif mock_entry_count:
        status = "mock"
    elif seed_only_count:
        status = "mixed"
    else:
        status = "live"
    return {
        "registry_count": registry_count,
        "live_verified_count": live_verified_count,
        "seed_only_count": seed_only_count,
        "mock_entry_count": mock_entry_count,
        "live_coverage_ratio": live_coverage_ratio,
        "cited_entry_count": cited_entry_count,
        "unused_registry_count": unused_registry_count,
        "cited_live_verified_count": cited_live_verified_count,
        "cited_mixed_count": cited_mixed_count,
        "cited_curated_seed_count": cited_curated_seed_count,
        "cited_mock_count": cited_mock_count,
        "status": status,
    }
