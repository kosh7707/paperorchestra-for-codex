from __future__ import annotations

from paperorchestra.reviews import citation_quality_classification as quality_classification


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
