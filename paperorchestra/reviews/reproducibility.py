from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.validator import (
    canonical_citation_key,
    canonical_citation_keys,
    canonical_citation_map,
    extract_citation_keys,
)
from paperorchestra.runtime.parity import build_lane_manifest_summary, write_lane_manifest_summary


STRICT_VALIDATION_WARNING_CODES = {"unsupported_comparative_claim"}


STRICT_FIGURE_WARNING_CODES = {
    "after_conclusion",
    "far_from_first_reference",
    "tail_clump",
    "wide_figure_mismatch",
}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _strict_content_gates_enabled() -> bool:
    return _env_flag("PAPERO_STRICT_CONTENT_GATES")


def _read_json_if_exists(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        payload = read_json(candidate)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_json_payload_if_exists(path: str | Path | None) -> Any | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        return read_json(candidate)
    except Exception:
        return None


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_optional_int(value: Any) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _is_optional_real(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def _is_external_id_value(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _is_valid_verified_paper_payload(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if not isinstance(item.get("paper_id"), str) or not item["paper_id"].strip():
        return False
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        return False
    if not _is_optional_int(item.get("year")):
        return False
    if item.get("publication_date") is not None and not isinstance(item.get("publication_date"), str):
        return False
    if item.get("venue") is not None and not isinstance(item.get("venue"), str):
        return False
    if not isinstance(item.get("abstract"), str):
        return False
    if not _is_string_list(item.get("authors")):
        return False
    if not _is_optional_int(item.get("citation_count")):
        return False
    if item.get("external_ids") is not None and not (
        isinstance(item.get("external_ids"), dict)
        and all(isinstance(key, str) and _is_external_id_value(value) for key, value in item["external_ids"].items())
    ):
        return False
    if item.get("url") is not None and not isinstance(item.get("url"), str):
        return False
    if not isinstance(item.get("bibtex_key"), str) or not item["bibtex_key"].strip():
        return False
    if item.get("alias_bibtex_keys") is not None and not _is_string_list(item.get("alias_bibtex_keys")):
        return False
    if item.get("origin") is not None and not isinstance(item.get("origin"), str):
        return False
    if item.get("matched_query") is not None and not isinstance(item.get("matched_query"), str):
        return False
    if not _is_optional_real(item.get("title_match_ratio")):
        return False
    if item.get("is_after_cutoff") is not None and not isinstance(item.get("is_after_cutoff"), bool):
        return False
    return True


def _is_valid_citation_map_entry(key: Any, entry: Any) -> bool:
    if not isinstance(key, str) or not key.strip():
        return False
    if not isinstance(entry, dict):
        return False
    if not isinstance(entry.get("title"), str) or not entry["title"].strip():
        return False
    if entry.get("abstract") is not None and not isinstance(entry.get("abstract"), str):
        return False
    if entry.get("authors") is not None and not _is_string_list(entry.get("authors")):
        return False
    if not _is_optional_int(entry.get("year")):
        return False
    if entry.get("venue") is not None and not isinstance(entry.get("venue"), str):
        return False
    if entry.get("paper_id") is not None and not isinstance(entry.get("paper_id"), str):
        return False
    if entry.get("origin") is not None and not isinstance(entry.get("origin"), str):
        return False
    if entry.get("matched_query") is not None and not isinstance(entry.get("matched_query"), str):
        return False
    provenance = entry.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        return False
    return True


def _bibtex_keys_from_text(text: str) -> set[str]:
    return set(re.findall(r"(?m)^\s*@[A-Za-z]+\s*\{\s*([^,\s]+)", text))


def _citation_keys_from_latex(path: str | Path | None) -> set[str]:
    if not path:
        return set()
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return set()
    return extract_citation_keys(candidate.read_text(encoding="utf-8", errors="replace"))


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


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


def _lane_completed(lane_summary: dict[str, Any], *stages: str) -> bool:
    stage_map = lane_summary.get("stages")
    if not isinstance(stage_map, dict):
        return False
    return any(
        isinstance(stage_map.get(stage), dict) and stage_map[stage].get("status") == "completed"
        for stage in stages
    )


def _prompt_trace_files(path: str | Path | None) -> list[Path]:
    if not path:
        return []
    directory = Path(path)
    if not directory.exists() or not directory.is_dir():
        return []
    return sorted(p for p in directory.glob('*.md') if p.is_file())


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


def _has_mock_watermark(paper_path: str | Path | None) -> bool:
    if not paper_path:
        return False
    candidate = Path(paper_path)
    if not candidate.exists():
        return False
    text = candidate.read_text(encoding='utf-8', errors='replace')
    return 'DO NOT DISTRIBUTE AS A FACTUAL DRAFT.' in text


def _current_validation_paths(state, session_artifact_dir: Path | None) -> list[Path]:
    paths: list[Path] = []
    if state.artifacts.latest_validation_json:
        paths.append(Path(state.artifacts.latest_validation_json))
    elif session_artifact_dir is not None and session_artifact_dir.exists():
        for name in ("validation.refine.iter-*.json", "validation.sections.json", "validation.intro_related.json"):
            matches = sorted(session_artifact_dir.glob(name))
            if matches:
                paths.append(matches[-1])
                break
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def _validation_warning_reports(state, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    if session_artifact_dir is None or not session_artifact_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    expected_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    for path in _current_validation_paths(state, session_artifact_dir):
        payload = _read_json_if_exists(path)
        if not payload:
            continue
        if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
            continue
        warning_count = int(payload.get("warning_count") or 0)
        if warning_count <= 0:
            continue
        reports.append(
            {
                "path": str(path),
                "stage": payload.get("stage"),
                "warning_count": warning_count,
                "warning_summary": payload.get("warning_summary", []),
            }
        )
    return reports


def _strict_content_gate_issues(state, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    expected_manuscript_sha = _file_sha256(state.artifacts.paper_full_tex)
    found_validation_report = False
    if session_artifact_dir is not None and session_artifact_dir.exists():
        for path in _current_validation_paths(state, session_artifact_dir):
            payload = _read_json_if_exists(path)
            if not payload:
                continue
            found_validation_report = True
            if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
                issues.append(
                    {
                        "source": str(path),
                        "stage": payload.get("stage"),
                        "kind": "validation_report_stale",
                        "code": "validation_report_stale",
                        "message": "Current validation report is missing or stale for the current manuscript.",
                        "severity": "error",
                    }
                )
                continue
            for issue in payload.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                code = issue.get("code")
                if code in STRICT_VALIDATION_WARNING_CODES:
                    issues.append(
                        {
                            "source": str(path),
                            "stage": payload.get("stage"),
                            "kind": "validation_warning",
                            "code": code,
                            "message": issue.get("message"),
                            "severity": issue.get("severity"),
                        }
                    )
    if state.artifacts.paper_full_tex and expected_manuscript_sha and not found_validation_report:
        issues.append(
            {
                "source": None,
                "stage": "validation",
                "kind": "validation_report_missing",
                "code": "validation_report_missing",
                "message": "Strict content gates require a current validation report for the manuscript.",
                "severity": "error",
            }
        )

    figure_review_candidates: list[Path] = []
    if state.artifacts.latest_figure_placement_review_json:
        figure_review_candidates.append(Path(state.artifacts.latest_figure_placement_review_json))
    if session_artifact_dir is not None:
        figure_review_candidates.append(session_artifact_dir / "figure-placement-review.json")

    seen_paths: set[Path] = set()
    found_figure_review = False
    for path in figure_review_candidates:
        resolved = path.resolve()
        if resolved in seen_paths or not path.exists():
            continue
        seen_paths.add(resolved)
        payload = _read_json_if_exists(path)
        if not payload:
            continue
        found_figure_review = True
        if expected_manuscript_sha and payload.get("manuscript_sha256") != expected_manuscript_sha:
            issues.append(
                {
                    "source": str(path),
                    "stage": "figure_placement",
                    "kind": "figure_placement_review_stale",
                    "code": "figure_placement_review_stale",
                    "message": "Figure placement review is missing or stale for the current manuscript.",
                    "severity": "error",
                }
            )
            continue
        for failure in payload.get("failures") or []:
            if not isinstance(failure, dict):
                continue
            code = failure.get("code")
            if not code:
                continue
            issues.append(
                {
                    "source": str(path),
                    "stage": "figure_placement",
                    "kind": "figure_placement_failure",
                    "code": code,
                    "message": failure.get("message"),
                    "severity": "error",
                }
            )
        for warning in payload.get("warnings") or []:
            if not isinstance(warning, dict):
                continue
            code = warning.get("code")
            if code in STRICT_FIGURE_WARNING_CODES:
                issues.append(
                    {
                        "source": str(path),
                        "stage": "figure_placement",
                        "kind": "figure_placement_warning",
                        "code": code,
                        "message": warning.get("message"),
                        "severity": "warning",
                    }
                )
    if state.artifacts.paper_full_tex and expected_manuscript_sha and not found_figure_review:
        issues.append(
            {
                "source": None,
                "stage": "figure_placement",
                "kind": "figure_placement_review_missing",
                "code": "figure_placement_review_missing",
                "message": "Strict content gates require a current figure-placement review for the manuscript.",
                "severity": "error",
            }
        )
    return issues


def _note_occurrence_count(notes: list[str], needle: str) -> int:
    return sum(1 for note in notes if needle in note)


def build_reproducibility_audit(cwd: str | Path | None, *, require_live_verification: bool = False) -> dict[str, Any]:
    state = load_session(cwd)
    lane_summary = build_lane_manifest_summary(cwd)
    session_artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent if state.artifacts.paper_full_tex else None
    runtime_parity = _read_json_if_exists(state.artifacts.latest_runtime_parity_json)
    if runtime_parity is None and session_artifact_dir is not None:
        runtime_parity = _read_json_if_exists(session_artifact_dir / "runtime-parity.json")
    provider_identity = _read_json_if_exists(state.artifacts.latest_provider_identity_json)
    compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
    prompt_trace_dir = state.artifacts.latest_prompt_trace_dir or (str(session_artifact_dir / "prompts") if session_artifact_dir else None)
    prompt_files = _prompt_trace_files(prompt_trace_dir)
    mock_registry_count = _mock_registry_entry_count(state.artifacts.citation_registry_json)
    citation_live_provenance = _citation_registry_live_provenance(
        state.artifacts.citation_registry_json,
        state.artifacts.paper_full_tex,
    )
    citation_support_review_provenance = _citation_support_review_provenance(cwd, state, session_artifact_dir)
    citation_surface = _citation_surface_health(state)
    validation_warning_reports = _validation_warning_reports(state, session_artifact_dir)
    validation_warning_count = sum(item["warning_count"] for item in validation_warning_reports)
    strict_content_gates = _strict_content_gates_enabled()
    strict_content_gate_issues = _strict_content_gate_issues(state, session_artifact_dir) if strict_content_gates else []
    refinement_compile_preservation_count = _note_occurrence_count(
        state.notes,
        "Compile-failed refinement iteration",
    )
    verification_invoked = state.latest_verify_mode is not None

    block_reasons: list[str] = []
    warn_reasons: list[str] = []

    if not prompt_files:
        block_reasons.append('Prompt trace artifacts are missing; stage prompts cannot be audited after the fact.')
    if state.latest_runtime_mode == 'omx_native' and lane_summary.get('fallback_count', 0) > 0:
        block_reasons.append('OMX-native run used fallback execution in one or more lane manifests.')
    if state.latest_verify_fallback_used == 'mock':
        block_reasons.append('Live verification fell back to mock verification.')
    if state.latest_provider_name == 'mock':
        block_reasons.append('Provider was mock; manuscript output is not a live factual draft.')
    if state.latest_verify_mode == 'mock':
        block_reasons.append('Citation verification used mock mode.')
    cited_mock_count = int(citation_live_provenance.get("cited_mock_count") or 0)
    if cited_mock_count > 0:
        block_reasons.append(f'Cited citation registry contains {cited_mock_count} mock entry/entries.')
    citation_lane_completed = _lane_completed(lane_summary, "literature", "verify")
    if citation_surface["issues"] and (
        verification_invoked
        or state.artifacts.references_bib
        or state.artifacts.paper_full_tex
        or citation_lane_completed
    ):
        prefix = "Citation lane completed but final citation artifacts are incomplete or malformed" if citation_lane_completed else "Final citation artifacts are incomplete or malformed"
        block_reasons.append(
            prefix + ": " + "; ".join(citation_surface["issues"])
        )

    if require_live_verification and not verification_invoked:
        block_reasons.append(
            "Live citation verification was required for this audit, but no live verification stage was invoked."
        )
    if (
        require_live_verification
        and verification_invoked
        and state.latest_verify_mode == "live"
        and citation_live_provenance.get("cited_curated_seed_count", citation_live_provenance.get("seed_only_count", 0)) > 0
    ):
        cited_curated_seed_count = citation_live_provenance.get("cited_curated_seed_count", citation_live_provenance.get("seed_only_count", 0))
        block_reasons.append(
            "Live citation verification was required, but "
            f"{cited_curated_seed_count} cited reference"
            f"{' is' if cited_curated_seed_count == 1 else 's are'} "
            "still seed-only or curated metadata without live verification."
        )
    if (
        require_live_verification
        and verification_invoked
        and state.latest_verify_mode == "live"
        and citation_live_provenance.get("cited_mixed_count", 0) > 0
    ):
        cited_mixed_count = citation_live_provenance.get("cited_mixed_count", 0)
        block_reasons.append(
            "Live citation verification was required, but "
            f"{cited_mixed_count} cited reference"
            f"{' has' if cited_mixed_count == 1 else 's have'} "
            "mixed cited provenance that needs explicit operator acceptance."
        )
    if (
        not require_live_verification
        and not verification_invoked
        and state.latest_discovery_mode in {"manual_bibtex", "manual_seed", "codex_web_seed"}
    ):
        skipped_verification_reason = (
            "Live citation verification was never invoked for this session; citation coverage is curated metadata rather than verified search results."
        )
        warn_reasons.append(skipped_verification_reason)
    if runtime_parity and runtime_parity.get('overall_status') != 'implemented':
        warn_reasons.append(f"Runtime parity status is {runtime_parity.get('overall_status')}, not implemented.")
    if compile_report and not compile_report.get('clean'):
        warn_reasons.append('Latest compile report is not clean.')
    if lane_summary.get('manifest_count', 0) == 0:
        warn_reasons.append('No lane manifests were recorded for the current session.')
    if validation_warning_count > 0:
        warn_reasons.append(f'{validation_warning_count} non-blocking validation warning(s) were recorded for the current session.')
    if strict_content_gates and strict_content_gate_issues:
        codes = ", ".join(sorted({str(issue.get("code")) for issue in strict_content_gate_issues}))
        block_reasons.append(f"Strict content gates blocked warning code(s): {codes}.")
    if refinement_compile_preservation_count > 0:
        warn_reasons.append(
            f'{refinement_compile_preservation_count} refinement iteration(s) preserved the prior compiled manuscript after compile failure.'
        )

    if (state.latest_provider_name == 'mock' or state.latest_verify_mode == 'mock' or state.latest_verify_fallback_used == 'mock') and not _has_mock_watermark(state.artifacts.paper_full_tex):
        warn_reasons.append('Mock or fallback-generated draft is missing the expected manuscript watermark.')

    verdict = 'BLOCK' if block_reasons else 'WARN' if warn_reasons else 'OK'
    source_artifacts = {
        'paper_full_tex': state.artifacts.paper_full_tex,
        'citation_registry_json': state.artifacts.citation_registry_json,
        'citation_map_json': state.artifacts.citation_map_json,
        'references_bib': state.artifacts.references_bib,
        'latest_provider_identity_json': state.artifacts.latest_provider_identity_json,
        'latest_figure_placement_review_json': state.artifacts.latest_figure_placement_review_json,
        'latest_runtime_parity_json': state.artifacts.latest_runtime_parity_json or (str(session_artifact_dir / "runtime-parity.json") if session_artifact_dir else None),
        'latest_compile_report_json': state.artifacts.latest_compile_report_json,
        'latest_prompt_trace_dir': prompt_trace_dir,
        'latest_lane_summary_json': state.artifacts.latest_lane_summary_json,
    }
    return {
        'session_id': state.session_id,
        'verdict': verdict,
        'reasons': block_reasons + warn_reasons,
        'blocking_reasons': block_reasons,
        'warning_reasons': warn_reasons,
        'source_artifacts': source_artifacts,
        'lane_manifest_summary': lane_summary,
        'runtime_parity': runtime_parity,
        'provider_identity': provider_identity,
        'generation_determinism': {
            'byte_identical_generation_claimed': False,
            'auditability_claimed': True,
            'rationale': (
                'PaperOrchestra reproducibility audits track inputs, provider/runtime identity, '
                'prompt traces, validation results, and artifact health; they do not promise '
                'byte-identical LLM text generation.'
            ),
        },
        'latest_provider_name': state.latest_provider_name,
        'latest_runtime_mode': state.latest_runtime_mode,
        'require_live_verification': require_live_verification,
        'verification_invoked': verification_invoked,
        'latest_verify_mode': state.latest_verify_mode,
        'latest_verify_fallback_used': state.latest_verify_fallback_used,
        'prompt_trace_file_count': len(prompt_files),
        'mock_registry_entry_count': mock_registry_count,
        'semantic_scholar_required': bool(citation_support_review_provenance.get("semantic_scholar_required")),
        'citation_support_review_live': bool(citation_support_review_provenance.get("live")),
        'citation_support_review_provenance': citation_support_review_provenance,
        'citation_live_provenance': citation_live_provenance,
        'citation_registry_live_verified_count': citation_live_provenance.get("live_verified_count", 0),
        'citation_registry_entry_count': citation_surface["registry_entry_count"],
        'citation_map_entry_count': citation_surface["citation_map_entry_count"],
        'references_bib_entry_count': citation_surface["references_bib_entry_count"],
        'citation_artifact_issues': citation_surface["issues"],
        'paper_has_mock_watermark': _has_mock_watermark(state.artifacts.paper_full_tex),
        'validation_warning_count': validation_warning_count,
        'validation_warning_reports': validation_warning_reports,
        'strict_content_gates': strict_content_gates,
        'strict_content_gate_issues': strict_content_gate_issues,
        'refinement_compile_preservation_count': refinement_compile_preservation_count,
    }


def write_reproducibility_audit(
    cwd: str | Path | None,
    output_path: str | Path | None = None,
    *,
    require_live_verification: bool = False,
) -> tuple[Path, dict[str, Any]]:
    lane_summary_path, lane_summary_payload = write_lane_manifest_summary(cwd)
    payload = build_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    payload['source_artifacts']['latest_lane_summary_json'] = str(lane_summary_path)
    payload['lane_manifest_summary'] = lane_summary_payload
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, 'reproducibility.audit.json')
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.latest_lane_summary_json = str(lane_summary_path)
    state.artifacts.latest_reproducibility_json = str(path)
    state.notes.append(f'Reproducibility audit recorded: {path.name}')
    save_session(cwd, state)
    return path, payload
