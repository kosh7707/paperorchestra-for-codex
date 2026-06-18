from __future__ import annotations

from typing import Any

from paperorchestra.reviews.reproducibility_payload_primitives import _is_optional_int, _is_string_list


def _is_valid_citation_map_entry(key: Any, entry: Any) -> bool:
    if not isinstance(key, str) or not key.strip():
        return False
    if not isinstance(entry, dict):
        return False
    if not isinstance(entry.get("title"), str) or not entry["title"].strip():
        return False
    if entry.get("abstract") is not None and not isinstance(entry.get("abstract"), str):
        return False
    if entry.get("authors") is not None and not _is_string_list(entry.get("authors")):
        return False
    if not _is_optional_int(entry.get("year")):
        return False
    if entry.get("venue") is not None and not isinstance(entry.get("venue"), str):
        return False
    if entry.get("paper_id") is not None and not isinstance(entry.get("paper_id"), str):
        return False
    if entry.get("origin") is not None and not isinstance(entry.get("origin"), str):
        return False
    if entry.get("matched_query") is not None and not isinstance(entry.get("matched_query"), str):
        return False
    provenance = entry.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        return False
    return True
