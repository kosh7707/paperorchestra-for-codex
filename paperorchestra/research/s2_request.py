from __future__ import annotations

import urllib.parse
from typing import Any


def s2_headers(*, api_key: str | None, user_agent: str) -> dict[str, str]:
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def s2_url(base_url: str, path: str, params: dict[str, Any] | None = None) -> str:
    normalized_path = path if path.startswith("/") else "/" + path
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    return f"{base_url.rstrip('/')}{normalized_path}" + (f"?{query}" if query else "")
