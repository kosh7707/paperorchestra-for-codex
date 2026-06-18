from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.reviews import citation_quality_classification as quality_classification
from paperorchestra.reviews import citation_quality_report as quality_report
from paperorchestra.reviews import citation_quality_support as quality_support
from paperorchestra.reviews.citation_integrity_paths import citation_integrity_audit_path, citation_source_match_path
from paperorchestra.reviews.citation_quality_report import CitationQualityGateReport, CitationQualityItem
from paperorchestra.reviews.citation_rendered_references import rendered_reference_audit_path


def build_citation_quality_gate(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    return build_citation_quality_gate_internal(cwd, quality_mode=quality_mode)["public_report"]


def build_citation_quality_gate_internal(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    mode = _normalize_quality_mode(quality_mode)
    state = load_session(cwd)
    paper = Path(state.artifacts.paper_full_tex).resolve() if state.artifacts.paper_full_tex else None
    if paper is None or not paper.exists():
        return _missing_manuscript_payload(mode)

    manuscript_sha = _file_sha256(paper)
    paths = _citation_quality_source_paths(cwd, paper)
    sources = _citation_quality_sources(state, paths)
    hard = _stale_codes(
        {
            "rendered_reference_audit": sources["rendered"],
            "citation_source_match": sources["source_match"],
            "citation_integrity_audit": sources["integrity"],
        },
        manuscript_sha,
        claim_safe=mode == "claim_safe",
    )
    warnings: list[str] = []
    items, item_hard, item_warnings = _citation_quality_items(mode=mode, sources=sources, support_run_root=paths["citation_support_review"].parent.parent)
    hard.extend(item_hard)
    warnings.extend(item_warnings)
    integrity_warnings = quality_classification._integrity_warning_codes(sources["integrity"])
    warnings.extend(integrity_warnings)
    report = CitationQualityGateReport(
        status="fail" if sorted(dict.fromkeys(hard)) else "warn" if sorted(dict.fromkeys(warnings)) else "pass",
        quality_mode=mode,
        manuscript_sha256=manuscript_sha,
        hard_gate_failures=sorted(dict.fromkeys(hard)),
        warning_codes=sorted(dict.fromkeys(warnings)),
        counts=quality_classification._counts(items, sources["integrity"]),
        items=items,
        source_artifact_hashes={name: _file_sha256(path) for name, path in paths.items()},
    )
    payload = report.to_internal_dict()
    quality_report._assert_public_safe(payload["public_report"])
    return payload


def _missing_manuscript_payload(mode: str) -> dict[str, Any]:
    report = CitationQualityGateReport(
        status="fail",
        quality_mode=mode,
        manuscript_sha256=None,
        hard_gate_failures=["citation_quality_manuscript_missing"],
        warning_codes=[],
        counts=quality_classification._empty_counts(),
        source_artifact_hashes={},
    )
    payload = report.to_internal_dict()
    quality_report._assert_public_safe(payload["public_report"])
    return payload


def _citation_quality_source_paths(cwd: str | Path | None, paper: Path) -> dict[str, Path]:
    return {
        "rendered_reference_audit": rendered_reference_audit_path(cwd),
        "citation_support_review": paper.parent / "citation_support_review.json",
        "citation_source_match": citation_source_match_path(cwd),
        "citation_integrity_audit": citation_integrity_audit_path(cwd),
    }


def _citation_quality_sources(state: Any, paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "rendered": _read_json_if_exists(paths["rendered_reference_audit"]),
        "support": _read_json_if_exists(paths["citation_support_review"]),
        "source_match": _read_json_if_exists(paths["citation_source_match"]),
        "integrity": _read_json_if_exists(paths["citation_integrity_audit"]),
        "claim_map": _read_json_if_exists(state.artifacts.claim_map_json),
        "placement": _read_json_if_exists(state.artifacts.citation_placement_plan_json),
    }


def _citation_quality_items(*, mode: str, sources: dict[str, Any], support_run_root: Path) -> tuple[list[CitationQualityItem], list[str], list[str]]:
    rendered = sources["rendered"]
    rendered_missing = not isinstance(rendered, dict)
    unknown_keys = quality_classification._string_set(rendered.get("unknown_metadata_keys") if isinstance(rendered, dict) else [])
    missing_keys = quality_classification._string_set(rendered.get("missing_bib_keys_for_cites") if isinstance(rendered, dict) else [])
    weak_identity_keys = quality_classification._string_set(rendered.get("weak_identity_keys") if isinstance(rendered, dict) else [])
    visible_keys = quality_classification._string_set(rendered.get("visible_reference_keys") if isinstance(rendered, dict) else [])
    support_items = quality_support._support_items(sources["support"], run_root=support_run_root)
    support_by_key = quality_support._support_by_key(support_items)
    claims_by_key = quality_classification._claims_by_key(sources["claim_map"])
    roles_by_key = quality_classification._roles_by_key(sources["placement"])
    all_keys = sorted(visible_keys | set(support_by_key) | set(claims_by_key) | unknown_keys | missing_keys | weak_identity_keys)

    items: list[CitationQualityItem] = []
    hard: list[str] = []
    warnings: list[str] = []
    for key in all_keys:
        for item, key_failures, key_warnings in _quality_items_for_key(
            key=key,
            mode=mode,
            rendered_missing=rendered_missing,
            unknown_keys=unknown_keys,
            missing_keys=missing_keys,
            weak_identity_keys=weak_identity_keys,
            support_by_key=support_by_key,
            claims_by_key=claims_by_key,
            roles_by_key=roles_by_key,
        ):
            hard.extend(key_failures)
            warnings.extend(key_warnings)
            items.append(item)
    return items, hard, warnings


def _quality_items_for_key(
    *,
    key: str,
    mode: str,
    rendered_missing: bool,
    unknown_keys: set[str],
    missing_keys: set[str],
    weak_identity_keys: set[str],
    support_by_key: dict[str, list[dict[str, Any]]],
    claims_by_key: dict[str, list[dict[str, Any]]],
    roles_by_key: dict[str, set[str]],
) -> list[tuple[CitationQualityItem, list[str], list[str]]]:
    critical = quality_classification._is_critical_key(
        key,
        support_by_key.get(key, []),
        claims_by_key.get(key, []),
        roles_by_key.get(key, set()),
        mode=mode,
        metadata_problem=rendered_missing or key in unknown_keys or key in missing_keys,
    )
    explicit_noncritical = quality_classification._is_explicitly_noncritical(claims_by_key.get(key, []), roles_by_key.get(key, set()))
    metadata_status = "missing" if key in missing_keys else "unknown" if rendered_missing or key in unknown_keys else "known"
    weak_identity = key in weak_identity_keys
    result: list[tuple[CitationQualityItem, list[str], list[str]]] = []
    for group_index, key_support_items in enumerate(quality_support._support_groups_for_quality_items(support_by_key.get(key, []))):
        support_status = quality_support._worst_support_status(key_support_items)
        key_failures, key_warnings = _quality_codes_for_key(
            critical=critical,
            explicit_noncritical=explicit_noncritical,
            metadata_status=metadata_status,
            weak_identity=weak_identity,
            support_status=support_status,
            support_missing=not key_support_items,
            rendered_missing=rendered_missing,
            mode=mode,
        )
        severity = "blocker" if key_failures else "warning" if key_warnings else "info"
        result.append(
            (
                CitationQualityItem(
                    item_id=quality_support._quality_item_id(key, key_support_items, group_index=group_index),
                    citation_key=key,
                    claim_id=quality_classification._first_claim_id(claims_by_key.get(key, [])),
                    citation_key_sha256=quality_classification._sha256_text(key),
                    critical=critical,
                    need_status="required" if critical else "optional" if explicit_noncritical else "unknown",
                    support_status=support_status,
                    metadata_status=metadata_status,
                    severity=severity,
                    failing_codes=sorted(dict.fromkeys(key_failures)),
                    warning_codes=sorted(dict.fromkeys(key_warnings)),
                    public_case=quality_support._public_case_id(key_support_items, claims_by_key.get(key, [])),
                    public_failure_code=quality_support._public_failure_code(key_support_items, key_failures),
                    public_failure_message=quality_support._public_failure_message(key_support_items, key_failures),
                ),
                key_failures,
                key_warnings,
            )
        )
    return result


def _quality_codes_for_key(
    *,
    critical: bool,
    explicit_noncritical: bool,
    metadata_status: str,
    weak_identity: bool,
    support_status: str,
    support_missing: bool,
    rendered_missing: bool,
    mode: str,
) -> tuple[list[str], list[str]]:
    key_failures: list[str] = []
    key_warnings: list[str] = []
    if critical:
        if rendered_missing and mode == "claim_safe":
            key_failures.append("critical_citation_metadata_missing")
        elif metadata_status == "missing":
            key_failures.append("critical_missing_bib_entry")
        elif metadata_status == "unknown":
            key_failures.append("critical_unknown_reference")
        if weak_identity:
            key_failures.append("critical_weak_reference_identity")
        if support_missing and mode == "claim_safe":
            key_failures.append("critical_citation_support_missing")
        elif support_status in quality_classification._UNSUPPORTED_STATUSES:
            key_failures.append("critical_unsupported_citation")
    elif metadata_status == "missing":
        key_warnings.append("noncritical_missing_bib_entry")
    elif metadata_status == "unknown" or explicit_noncritical:
        if metadata_status == "unknown":
            key_warnings.append("noncritical_unknown_reference")
    if weak_identity and not critical:
        key_warnings.append("noncritical_weak_reference_identity")
    return key_failures, key_warnings


def _normalize_quality_mode(value: str) -> str:
    return value if value in {"draft", "ralph", "claim_safe"} else "ralph"


def _stale_codes(payloads: dict[str, Any], manuscript_sha: str | None, *, claim_safe: bool) -> list[str]:
    if not claim_safe or not manuscript_sha:
        return []
    stale: list[str] = []
    for payload in payloads.values():
        if not isinstance(payload, dict):
            continue
        bound = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
        if bound and bound != manuscript_sha:
            stale.append("citation_quality_stale")
    return sorted(dict.fromkeys(stale))
