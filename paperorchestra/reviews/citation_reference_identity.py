from __future__ import annotations

from paperorchestra.reviews.citation_reference_duplicates import _duplicate_reference_identity_groups
from paperorchestra.reviews.citation_reference_normalizers import (
    _hash_identity,
    _namespace_for_report,
    _normalize_doi,
    _normalize_eprint,
    _normalize_report_number,
    _normalize_url_for_identity,
    _reference_identity_label,
    _standard_identity_from_text,
)
from paperorchestra.reviews.citation_reference_unknowns import (
    REFERENCE_IDENTITY_FALLBACK_FIELDS as _REFERENCE_IDENTITY_FALLBACK_FIELDS,
    STABLE_REFERENCE_IDENTITY_FIELDS as _STABLE_REFERENCE_IDENTITY_FIELDS,
    _entry_has_stable_identity,
    _entry_unknown_fields,
    _has_known_field,
    _is_unknown_value,
)

__all__ = [
    "_REFERENCE_IDENTITY_FALLBACK_FIELDS",
    "_STABLE_REFERENCE_IDENTITY_FIELDS",
    "_duplicate_reference_identity_groups",
    "_entry_has_stable_identity",
    "_entry_unknown_fields",
    "_hash_identity",
    "_has_known_field",
    "_is_unknown_value",
    "_namespace_for_report",
    "_normalize_doi",
    "_normalize_eprint",
    "_normalize_report_number",
    "_normalize_url_for_identity",
    "_reference_identity_label",
    "_standard_identity_from_text",
]
