from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.reviews import citation_quality_classification as quality_classification
from paperorchestra.reviews import citation_quality_report as quality_report
from paperorchestra.reviews import citation_quality_support as quality_support
from paperorchestra.reviews.citation_quality_report import (
    CITATION_QUALITY_GATE_SCHEMA_VERSION,
    CitationQualityGateReport,
    CitationQualityItem,
)
from paperorchestra.reviews.citation_integrity import (
    citation_integrity_audit_path,
    citation_source_match_path,
    rendered_reference_audit_path,
)
from paperorchestra.core.io import write_json
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.core.session import artifact_path, load_session

CITATION_QUALITY_GATE_FILENAME = "citation_quality_gate.json"
CITATION_QUALITY_GATE_INTERNAL_FILENAME = "citation_quality_gate.internal.json"


def citation_quality_gate_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_QUALITY_GATE_FILENAME)


def citation_quality_gate_internal_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_QUALITY_GATE_INTERNAL_FILENAME)


def build_citation_quality_gate(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    return build_citation_quality_gate_internal(cwd, quality_mode=quality_mode)["public_report"]


def build_citation_quality_gate_internal(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    mode = _normalize_quality_mode(quality_mode)
    state = load_session(cwd)
    paper = Path(state.artifacts.paper_full_tex).resolve() if state.artifacts.paper_full_tex else None
    if paper is None or not paper.exists():
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

    manuscript_sha = _file_sha256(paper)
    rendered_path = rendered_reference_audit_path(cwd)
    support_path = paper.parent / "citation_support_review.json"
    source_match_path = citation_source_match_path(cwd)
    integrity_path = citation_integrity_audit_path(cwd)
    rendered = _read_json_if_exists(rendered_path)
    support = _read_json_if_exists(support_path)
    source_match = _read_json_if_exists(source_match_path)
    integrity = _read_json_if_exists(integrity_path)
    claim_map = _read_json_if_exists(state.artifacts.claim_map_json)
    placement = _read_json_if_exists(state.artifacts.citation_placement_plan_json)

    hard: list[str] = []
    warnings: list[str] = []
    stale_codes = _stale_codes(
        {
            "rendered_reference_audit": rendered,
            "citation_source_match": source_match,
            "citation_integrity_audit": integrity,
        },
        manuscript_sha,
        claim_safe=mode == "claim_safe",
    )
    hard.extend(stale_codes)

    rendered_missing = not isinstance(rendered, dict)
    unknown_keys = quality_classification._string_set(rendered.get("unknown_metadata_keys") if isinstance(rendered, dict) else [])
    missing_keys = quality_classification._string_set(rendered.get("missing_bib_keys_for_cites") if isinstance(rendered, dict) else [])
    weak_identity_keys = quality_classification._string_set(rendered.get("weak_identity_keys") if isinstance(rendered, dict) else [])
    visible_keys = quality_classification._string_set(rendered.get("visible_reference_keys") if isinstance(rendered, dict) else [])
    support_items = quality_support._support_items(support, run_root=support_path.parent.parent)
    support_by_key = quality_support._support_by_key(support_items)
    claims_by_key = quality_classification._claims_by_key(claim_map)
    roles_by_key = quality_classification._roles_by_key(placement)
    all_keys = sorted(visible_keys | set(support_by_key) | set(claims_by_key) | unknown_keys | missing_keys | weak_identity_keys)

    items: list[CitationQualityItem] = []
    for key in all_keys:
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
        for group_index, key_support_items in enumerate(quality_support._support_groups_for_quality_items(support_by_key.get(key, []))):
            support_status = quality_support._worst_support_status(key_support_items)
            support_missing = not key_support_items
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
            severity = "blocker" if key_failures else "warning" if key_warnings else "info"
            hard.extend(key_failures)
            warnings.extend(key_warnings)
            items.append(
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
                )
            )

    integrity_warnings = quality_classification._integrity_warning_codes(integrity)
    warnings.extend(integrity_warnings)
    counts = quality_classification._counts(items, integrity)
    hard_unique = sorted(dict.fromkeys(hard))
    warn_unique = sorted(dict.fromkeys(warnings))
    status = "fail" if hard_unique else "warn" if warn_unique else "pass"
    report = CitationQualityGateReport(
        status=status,
        quality_mode=mode,
        manuscript_sha256=manuscript_sha,
        hard_gate_failures=hard_unique,
        warning_codes=warn_unique,
        counts=counts,
        items=items,
        source_artifact_hashes={
            "rendered_reference_audit": _file_sha256(rendered_path),
            "citation_support_review": _file_sha256(support_path),
            "citation_source_match": _file_sha256(source_match_path),
            "citation_integrity_audit": _file_sha256(integrity_path),
        },
    )
    payload = report.to_internal_dict()
    quality_report._assert_public_safe(payload["public_report"])
    return payload


def write_citation_quality_gate(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    internal_payload = build_citation_quality_gate_internal(cwd, quality_mode=quality_mode)
    payload = internal_payload["public_report"]
    canonical_path = citation_quality_gate_path(cwd)
    path = Path(output_path).resolve() if output_path else canonical_path
    write_json(path, payload)
    if path.resolve() == canonical_path.resolve():
        write_json(citation_quality_gate_internal_path(cwd), internal_payload)
    return path, payload


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
