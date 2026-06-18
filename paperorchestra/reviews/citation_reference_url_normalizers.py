from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from paperorchestra.reviews.citation_reference_unknowns import _is_unknown_value

_SENSITIVE_QUERY_KEYS = {
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
    query = urlencode(sorted(_safe_query_items(parts.query)), doseq=True)
    return urlunsplit(("", f"{host}{port}", path, query, ""))


def _safe_query_items(query: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for key, item_value in parse_qsl(query, keep_blank_values=True):
        normalized_key = key.strip().lower()
        if any(marker in normalized_key for marker in _SENSITIVE_QUERY_KEYS):
            continue
        items.append((normalized_key, item_value.strip()))
    return items
