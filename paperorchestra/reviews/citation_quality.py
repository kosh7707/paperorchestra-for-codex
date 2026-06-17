from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.reviews.citation_quality_report import (
    CITATION_QUALITY_GATE_SCHEMA_VERSION,
    CitationQualityGateReport,
    CitationQualityItem,
    _assert_public_safe,
    _citation_summary_from_items,
    _default_public_failure_message,
    _public_failures,
    _public_values,
)
from paperorchestra.reviews.citation_quality_support import (
    _public_case_id,
    _public_failure_code,
    _public_failure_message,
    _quality_item_id,
    _support_by_key,
    _support_groups_for_quality_items,
    _support_items,
    _support_items_from_v3_cases,
    _v3_evidence_is_readable,
    _v3_support_status,
    _worst_support_status,
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
_HIGH_CRITICAL_TOKENS = {
    "critical",
    "high",
    "root",
    "central_support",
    "numeric",
    "comparative",
    "security",
    "novelty",
    "causal",
    "benchmark",
    "result",
}
_EXTERNAL_REQUIRED_SOURCE_TYPES = {
    "external_literature",
    "standard",
    "benchmark_reference",
    "prior_work",
}
_NONCRITICAL_TOKENS = {"background", "local", "optional", "low"}
_UNSUPPORTED_STATUSES = {"unsupported", "contradicted", "metadata_only", "insufficient_evidence"}
_WARNING_INTEGRITY_CODES = {
    "citation_duplicate_support",
    "citation_bomb_detected",
    "dense_citation_bundle_requires_role_check",
}

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
            counts=_empty_counts(),
            source_artifact_hashes={},
        )
        payload = report.to_internal_dict()
        _assert_public_safe(payload["public_report"])
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
    unknown_keys = _string_set(rendered.get("unknown_metadata_keys") if isinstance(rendered, dict) else [])
    missing_keys = _string_set(rendered.get("missing_bib_keys_for_cites") if isinstance(rendered, dict) else [])
    weak_identity_keys = _string_set(rendered.get("weak_identity_keys") if isinstance(rendered, dict) else [])
    visible_keys = _string_set(rendered.get("visible_reference_keys") if isinstance(rendered, dict) else [])
    support_items = _support_items(support, run_root=support_path.parent.parent)
    support_by_key = _support_by_key(support_items)
    claims_by_key = _claims_by_key(claim_map)
    roles_by_key = _roles_by_key(placement)
    all_keys = sorted(visible_keys | set(support_by_key) | set(claims_by_key) | unknown_keys | missing_keys | weak_identity_keys)

    items: list[CitationQualityItem] = []
    for key in all_keys:
        critical = _is_critical_key(
            key,
            support_by_key.get(key, []),
            claims_by_key.get(key, []),
            roles_by_key.get(key, set()),
            mode=mode,
            metadata_problem=rendered_missing or key in unknown_keys or key in missing_keys,
        )
        explicit_noncritical = _is_explicitly_noncritical(claims_by_key.get(key, []), roles_by_key.get(key, set()))
        metadata_status = "missing" if key in missing_keys else "unknown" if rendered_missing or key in unknown_keys else "known"
        weak_identity = key in weak_identity_keys
        for group_index, key_support_items in enumerate(_support_groups_for_quality_items(support_by_key.get(key, []))):
            support_status = _worst_support_status(key_support_items)
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
                elif support_status in _UNSUPPORTED_STATUSES:
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
                    item_id=_quality_item_id(key, key_support_items, group_index=group_index),
                    citation_key=key,
                    claim_id=_first_claim_id(claims_by_key.get(key, [])),
                    citation_key_sha256=_sha256_text(key),
                    critical=critical,
                    need_status="required" if critical else "optional" if explicit_noncritical else "unknown",
                    support_status=support_status,
                    metadata_status=metadata_status,
                    severity=severity,
                    failing_codes=sorted(dict.fromkeys(key_failures)),
                    warning_codes=sorted(dict.fromkeys(key_warnings)),
                    public_case=_public_case_id(key_support_items, claims_by_key.get(key, [])),
                    public_failure_code=_public_failure_code(key_support_items, key_failures),
                    public_failure_message=_public_failure_message(key_support_items, key_failures),
                )
            )

    integrity_warnings = _integrity_warning_codes(integrity)
    warnings.extend(integrity_warnings)
    counts = _counts(items, integrity)
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
    _assert_public_safe(payload["public_report"])
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


def _empty_counts() -> dict[str, int]:
    return {
        "critical_need_count": 0,
        "critical_unknown_reference_count": 0,
        "critical_unsupported_count": 0,
        "critical_weak_identity_count": 0,
        "noncritical_weak_identity_count": 0,
        "citation_bomb_count": 0,
        "duplicate_reference_count": 0,
    }


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


def _claims_by_key(payload: Any) -> dict[str, list[dict[str, Any]]]:
    claims = payload.get("claims") if isinstance(payload, dict) else None
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(claims, list):
        return result
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        for key in claim.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(claim)
    return result


def _roles_by_key(payload: Any) -> dict[str, set[str]]:
    placements = payload.get("placements") if isinstance(payload, dict) else None
    result: dict[str, set[str]] = {}
    if not isinstance(placements, list):
        return result
    for item in placements:
        if not isinstance(item, dict):
            continue
        keys = [str(item.get(field)).strip() for field in ("citation_key", "key") if item.get(field)]
        keys.extend(str(key).strip() for key in item.get("citation_keys") or [] if str(key).strip())
        roles: set[str] = set()
        for field in ("claim_id", "claim_ids", "citation_role", "citation_roles", "support_role", "claim_type", "criticality"):
            roles.update(_tokens(item.get(field)))
        for key in keys:
            result.setdefault(key, set()).update(roles)
    return result


def _is_critical_key(
    key: str,
    support_items: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    roles: set[str],
    *,
    mode: str,
    metadata_problem: bool,
) -> bool:
    if any(item.get("critical") is True for item in support_items):
        return True
    for item in support_items:
        if _tokens_for_fields(item, ("claim_type", "criticality", "citation_role", "support_role")) & _HIGH_CRITICAL_TOKENS:
            return True
    for claim in claims:
        if claim.get("required") is True or claim.get("citation_required") is True:
            return True
        if str(claim.get("required_source_type") or "").strip().lower() in _EXTERNAL_REQUIRED_SOURCE_TYPES:
            return True
        if _tokens_for_fields(claim, ("claim_type", "criticality", "graph_role")) & _HIGH_CRITICAL_TOKENS:
            return True
    if roles & _HIGH_CRITICAL_TOKENS:
        return True
    if mode == "claim_safe" and metadata_problem and not claims and not support_items:
        return True
    return False


def _is_explicitly_noncritical(claims: list[dict[str, Any]], roles: set[str]) -> bool:
    if roles & _HIGH_CRITICAL_TOKENS:
        return False
    if roles & _NONCRITICAL_TOKENS:
        return True
    if not claims:
        return False
    for claim in claims:
        if claim.get("required") is True or claim.get("citation_required") is True:
            return False
        if str(claim.get("required_source_type") or "").strip().lower() in _EXTERNAL_REQUIRED_SOURCE_TYPES:
            return False
        if _tokens_for_fields(claim, ("claim_type", "criticality", "graph_role")) & _HIGH_CRITICAL_TOKENS:
            return False
    return any(_tokens_for_fields(claim, ("claim_type", "criticality", "graph_role")) & _NONCRITICAL_TOKENS for claim in claims)


def _integrity_warning_codes(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    codes = _string_set(payload.get("failing_codes")) | _string_set(payload.get("warning_codes"))
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
    codes |= _string_set(density.get("warning_codes"))
    return sorted(code for code in codes if code in _WARNING_INTEGRITY_CODES)


def _counts(items: list[CitationQualityItem], integrity: Any) -> dict[str, int]:
    counts = _empty_counts()
    counts["critical_need_count"] = sum(1 for item in items if item.critical)
    counts["critical_unknown_reference_count"] = sum(
        1 for item in items if "critical_unknown_reference" in item.failing_codes or "critical_missing_bib_entry" in item.failing_codes
    )
    counts["critical_unsupported_count"] = sum(1 for item in items if "critical_unsupported_citation" in item.failing_codes)
    counts["critical_weak_identity_count"] = sum(1 for item in items if "critical_weak_reference_identity" in item.failing_codes)
    counts["noncritical_weak_identity_count"] = sum(1 for item in items if "noncritical_weak_reference_identity" in item.warning_codes)
    if isinstance(integrity, dict):
        checks = integrity.get("checks") if isinstance(integrity.get("checks"), dict) else {}
        density = checks.get("citation_density") if isinstance(checks.get("citation_density"), dict) else {}
        duplicate = checks.get("duplicate_support") if isinstance(checks.get("duplicate_support"), dict) else {}
        counts["citation_bomb_count"] = len(density.get("bomb_sentences") or []) + len(density.get("bomb_paragraph_key_sets") or [])
        counts["duplicate_reference_count"] = len(duplicate.get("duplicate_keys") or [])
    return counts


def _tokens_for_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for field in fields:
        result.update(_tokens(payload.get(field)))
    return result


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).strip().lower() for item in value if str(item).strip()}
    return {str(value).strip().lower()} if str(value).strip() else set()


def _first_claim_id(claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        claim_id = claim.get("id") or claim.get("claim_id")
        if claim_id:
            return str(claim_id)
    return None


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
