from __future__ import annotations

from typing import Any

from paperorchestra.reviews.reproducibility_payload_primitives import (
    _is_external_id_value,
    _is_optional_int,
    _is_optional_real,
    _is_string_list,
)


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
