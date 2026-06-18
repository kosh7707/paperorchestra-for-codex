from __future__ import annotations

import json
from typing import Any

from paperorchestra.research.prior_work_seed_normalization import _normalize_seed_entry


def _parse_json_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict):
        raw_entries = payload.get("references") or payload.get("papers") or payload.get("prior_work") or payload.get("entries") or []
    else:
        raw_entries = []
    result: list[dict[str, Any]] = []
    for item in raw_entries:
        if isinstance(item, dict):
            normalized = _normalize_seed_entry(item, default_source=default_source)
            if normalized:
                result.append(normalized)
    return result
