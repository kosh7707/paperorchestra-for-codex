from __future__ import annotations

import re
from typing import Any

from paperorchestra.manuscript.citations import extract_citation_keys


def _sentences_with_cites(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if "\\cite" in part]


def _cite_key_counts_from_text(text: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    sentences = _sentences_with_cites(text)
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for idx, sentence in enumerate(sentences, start=1):
        keys = sorted(extract_citation_keys(sentence))
        records.append({"id": f"tex-sentence-{idx}", "sentence": sentence, "citation_keys": keys})
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
    return records, counts


def _role_tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def _duplicate_support_failures(
    items: list[dict[str, Any]],
    text_counts: dict[str, int],
    placement_roles: dict[str, set[str]],
) -> list[str]:
    counts = dict(text_counts)
    roles_by_key: dict[str, set[str]] = {
        key: set(value) for key, value in placement_roles.items()
    }
    if items:
        counts = {}
        for item in items:
            keys = [str(key) for key in item.get("citation_keys") or []]
            item_roles = set()
            for field in ["claim_id", "claim_ids", "citation_role", "citation_roles", "support_role"]:
                item_roles.update(_role_tokens(item.get(field)))
            for key in keys:
                counts[key] = counts.get(key, 0) + 1
                roles_by_key.setdefault(key, set()).update(item_roles)
    return sorted(
        key for key, count in counts.items()
        if count > 3 and len(roles_by_key.get(key, set())) < 2
    )


def _section_for_sentence(latex: str, sentence: str) -> str | None:
    needle = sentence[:80]
    idx = latex.find(needle) if needle else -1
    if idx < 0:
        idx = latex.find(sentence[:30]) if sentence else -1
    before = latex[:idx] if idx >= 0 else latex
    sections = re.findall(r"\\(?:sub)*section\*?\{([^}]+)\}", before)
    return sections[-1].strip() if sections else None


def _support_items_by_sentence(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        sentence = str(item.get("sentence") or "").strip()
        if sentence:
            result.setdefault(sentence, []).append(item)
    return result


def _support_items_by_key(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        for key in item.get("citation_keys") or []:
            normalized = str(key).strip()
            if normalized:
                result.setdefault(normalized, []).append(item)
    return result


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("support_status") or "unknown").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))
