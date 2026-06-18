from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _is_unknown_value(value: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return normalized in {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def _entry_unknown_fields(entry: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if _is_unknown_value(str(entry.get("title") or "")):
        fields.append("title")
    if _is_unknown_value(str(entry.get("author") or entry.get("editor") or entry.get("organization") or "")):
        fields.append("author_or_organization")
    if _is_unknown_value(str(entry.get("year") or entry.get("date") or "")):
        fields.append("year_or_date")
    return fields


_STABLE_REFERENCE_IDENTITY_FIELDS = {
    "doi",
    "url",
    "eprint",
    "archiveprefix",
    "arxiv",
    "pmid",
    "pmcid",
    "isbn",
    "issn",
    "howpublished",
    "number",
    "reportnumber",
}
_REFERENCE_IDENTITY_FALLBACK_FIELDS = {
    "journal",
    "booktitle",
    "venue",
    "publisher",
    "institution",
    "organization",
    "school",
    "series",
}


def _has_known_field(entry: dict[str, Any], fields: set[str]) -> bool:
    for field in fields:
        value = entry.get(field)
        if value is not None and not _is_unknown_value(str(value)):
            return True
    return False


def _entry_has_stable_identity(entry: dict[str, Any]) -> bool:
    """Return whether a visible reference has enough identity to be auditable."""

    return _has_known_field(entry, _STABLE_REFERENCE_IDENTITY_FIELDS) or _has_known_field(
        entry,
        _REFERENCE_IDENTITY_FALLBACK_FIELDS,
    )


def _normalize_doi(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(" .;,")
    return text.lower() or None


def _normalize_url_for_identity(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or _is_unknown_value(text):
        return None
    parts = urlsplit(text if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text) else f"https://{text}")
    host = (parts.hostname or "").lower()
    if not host:
        return None
    port = f":{parts.port}" if parts.port else ""
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/") or "/"
    sensitive_query_keys = {
        "access_token",
        "api_key",
        "auth",
        "credential",
        "key",
        "pass",
        "passwd",
        "password",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
    }
    query_items = []
    for key, item_value in parse_qsl(parts.query, keep_blank_values=True):
        normalized_key = key.strip().lower()
        if any(marker in normalized_key for marker in sensitive_query_keys):
            continue
        query_items.append((normalized_key, item_value.strip()))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit(("", f"{host}{port}", path, query, ""))


def _hash_identity(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"


def _normalize_eprint(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    text = re.sub(r"^arxiv:", "", text, flags=re.IGNORECASE)
    return text.lower().strip(" .;,") or None


def _standard_identity_from_text(value: Any) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or _is_unknown_value(text):
        return None
    match = re.search(r"\b(rfc)\s*-?\s*(\d{3,5})\b", text, flags=re.IGNORECASE)
    if match:
        return f"standard:{match.group(1).lower()}-{match.group(2)}"
    return None


def _normalize_report_number(value: Any) -> str | None:
    text = re.sub(r"\s+", "-", str(value or "").strip().lower())
    text = re.sub(r"[^a-z0-9._-]+", "-", text).strip("-._")
    if not text or _is_unknown_value(text):
        return None
    return text


def _namespace_for_report(entry: dict[str, Any]) -> str | None:
    fields = ("organization", "institution", "venue", "journal", "booktitle", "series", "publisher", "school")
    values = [
        str(entry.get(field) or "").strip().lower()
        for field in fields
        if not _is_unknown_value(str(entry.get(field) or ""))
    ]
    if not values:
        return None
    namespace = re.sub(r"\s+", "-", values[0])
    namespace = re.sub(r"[^a-z0-9._-]+", "-", namespace).strip("-._")
    return namespace or None


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
        archive = str(entry.get("archiveprefix") or "eprint").strip().lower() or "eprint"
        archive = re.sub(r"[^a-z0-9._-]+", "-", archive).strip("-._") or "eprint"
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
