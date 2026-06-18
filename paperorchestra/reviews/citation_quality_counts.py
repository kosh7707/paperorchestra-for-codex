from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_quality_report import CitationQualityItem
from paperorchestra.reviews.citation_quality_tokens import _string_set

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
