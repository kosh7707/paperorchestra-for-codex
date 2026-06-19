from __future__ import annotations

from typing import Any

from paperorchestra.reviews.citation_reference_hashing import _hash_identity
from paperorchestra.reviews.citation_reference_identifier_normalizers import (
    _normalize_doi,
    _normalize_eprint,
    _standard_identity_from_text,
)
from paperorchestra.reviews.citation_reference_label import _reference_identity_label
from paperorchestra.reviews.citation_reference_report_normalizers import _namespace_for_report, _normalize_report_number
from paperorchestra.reviews.citation_reference_url_normalizers import _normalize_url_for_identity
from paperorchestra.reviews.citation_reference_unknowns import (
    REFERENCE_IDENTITY_FALLBACK_FIELDS as _REFERENCE_IDENTITY_FALLBACK_FIELDS,
    STABLE_REFERENCE_IDENTITY_FIELDS as _STABLE_REFERENCE_IDENTITY_FIELDS,
    _entry_has_stable_identity,
    _entry_unknown_fields,
    _has_known_field,
    _is_unknown_value,
)


def _duplicate_reference_identity_groups(visible_keys: list[str], entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_identity: dict[str, list[str]] = {}
    for key in visible_keys:
        entry = entries.get(key)
        if not entry:
            continue
        identity = _reference_identity_label(entry)
        if not identity:
            continue
        by_identity.setdefault(identity, []).append(key)
    groups = [
        {"identity": identity, "keys": sorted(dict.fromkeys(keys))}
        for identity, keys in by_identity.items()
        if len(set(keys)) > 1
    ]
    return sorted(groups, key=lambda group: (str(group["identity"]), list(group["keys"])))


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
