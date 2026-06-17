from __future__ import annotations

from typing import Any


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_optional_int(value: Any) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _is_optional_real(value: Any) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))


def _is_external_id_value(value: Any) -> bool:
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _is_valid_verified_paper_payload(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if not isinstance(item.get("paper_id"), str) or not item["paper_id"].strip():
        return False
    if not isinstance(item.get("title"), str) or not item["title"].strip():
        return False
    if not _is_optional_int(item.get("year")):
        return False
    if item.get("publication_date") is not None and not isinstance(item.get("publication_date"), str):
        return False
    if item.get("venue") is not None and not isinstance(item.get("venue"), str):
        return False
    if not isinstance(item.get("abstract"), str):
        return False
    if not _is_string_list(item.get("authors")):
        return False
    if not _is_optional_int(item.get("citation_count")):
        return False
    if item.get("external_ids") is not None and not (
        isinstance(item.get("external_ids"), dict)
        and all(isinstance(key, str) and _is_external_id_value(value) for key, value in item["external_ids"].items())
    ):
        return False
    if item.get("url") is not None and not isinstance(item.get("url"), str):
        return False
    if not isinstance(item.get("bibtex_key"), str) or not item["bibtex_key"].strip():
        return False
    if item.get("alias_bibtex_keys") is not None and not _is_string_list(item.get("alias_bibtex_keys")):
        return False
    if item.get("origin") is not None and not isinstance(item.get("origin"), str):
        return False
    if item.get("matched_query") is not None and not isinstance(item.get("matched_query"), str):
        return False
    if not _is_optional_real(item.get("title_match_ratio")):
        return False
    if item.get("is_after_cutoff") is not None and not isinstance(item.get("is_after_cutoff"), bool):
        return False
    return True


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
