from __future__ import annotations

import re
from typing import Any

from paperorchestra.reviews.citation_reference_hashing import _hash_identity
from paperorchestra.reviews.citation_reference_identifier_normalizers import (
    _normalize_doi,
    _normalize_eprint,
    _standard_identity_from_text,
)
from paperorchestra.reviews.citation_reference_report_normalizers import _namespace_for_report, _normalize_report_number
from paperorchestra.reviews.citation_reference_url_normalizers import _normalize_url_for_identity


def _reference_identity_label(entry: dict[str, Any]) -> str | None:
    doi = _normalize_doi(entry.get("doi"))
    if doi:
        return f"doi:{doi}"

    url = _normalize_url_for_identity(entry.get("url"))
    if url:
        return _hash_identity("url", url)

    arxiv = _normalize_eprint(entry.get("arxiv"))
    if arxiv:
        return f"arxiv:{arxiv}"

    eprint = _normalize_eprint(entry.get("eprint"))
    if eprint:
        archive = _normalized_archive_prefix(entry.get("archiveprefix"))
        return f"{archive}:{eprint}"

    for field in ("number", "reportnumber", "howpublished"):
        standard = _standard_identity_from_text(entry.get(field))
        if standard:
            return standard

    namespace = _namespace_for_report(entry)
    if namespace:
        for field in ("reportnumber", "number", "howpublished"):
            report_number = _normalize_report_number(entry.get(field))
            if report_number:
                return f"report:{namespace}:{report_number}"
    return None


def _normalized_archive_prefix(value: Any) -> str:
    archive = str(value or "eprint").strip().lower() or "eprint"
    return re.sub(r"[^a-z0-9._-]+", "-", archive).strip("-._") or "eprint"
