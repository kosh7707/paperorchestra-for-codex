from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.citation_gap_items import citation_support_gap_items
from paperorchestra.loop_engine.quality.citation_gap_policy import (
    classify_citation_support_gap_items,
    no_gap_items_classification,
    payload_unavailable_gap_classification,
)
from .utils import _read_json_if_exists


def _citation_support_gap_classification(citation_check: dict[str, Any]) -> dict[str, Any]:
    path = citation_check.get("path")
    payload = _read_json_if_exists(path) if isinstance(path, (str, Path)) else None
    if not isinstance(payload, dict):
        return payload_unavailable_gap_classification()
    items, v3_payload = citation_support_gap_items(payload)
    if not items:
        return no_gap_items_classification(v3_payload=v3_payload)
    return classify_citation_support_gap_items(items)

