from __future__ import annotations

from typing import Any

from paperorchestra.manuscript.citation_map_model import citation_entry_for_key
from paperorchestra.reviews.citation_source_fields import _clean_optional_string
from paperorchestra.reviews.citation_source_type import _source_type_for_entry

_SOURCE_PAYLOAD_FIELDS = {
    "title": ("title",),
    "url": ("url", "source_url"),
    "doi": ("doi", "DOI"),
    "arxiv": ("arxiv_id", "arxiv", "ArXiv"),
}


def _lean_source_payload(key: str, citation_map: dict[str, Any]) -> dict[str, Any]:
    entry = citation_entry_for_key(citation_map, key) if isinstance(citation_map, dict) else {}
    payload: dict[str, Any] = {"type": _source_type_for_entry(entry)}
    for out_key, fields in _SOURCE_PAYLOAD_FIELDS.items():
        value = _first_entry_value(entry, fields)
        if value:
            payload[out_key] = value
    if "title" not in payload:
        payload["title"] = key
    return payload


def _first_entry_value(entry: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = _clean_optional_string(entry.get(field))
        if value:
            return value
    return None
