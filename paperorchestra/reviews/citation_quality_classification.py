from __future__ import annotations

import hashlib
from typing import Any

from paperorchestra.reviews.citation_quality_report import CitationQualityItem

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
