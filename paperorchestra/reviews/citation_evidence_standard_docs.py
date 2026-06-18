from __future__ import annotations

import re
from typing import Any


def _normalize_evidence_identity(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _standard_doc_references(value: Any) -> set[tuple[str, str]]:
    normalized = _normalize_evidence_identity(value)
    refs: set[tuple[str, str]] = set()
    for match in re.finditer(r"\brfc\s*(\d+[a-z0-9]*)\b", normalized):
        refs.add(("rfc", match.group(1)))
    for match in re.finditer(
        r"\bnist\s+sp\s+(\d+(?:\s+\d+[a-z0-9]*)?)(?:\s+(?:part|pt)\s+(\d+))?(?:\s+rev\s+(\d+))?",
        normalized,
    ):
        identifier = " ".join(part for part in match.groups() if part).strip()
        if identifier:
            refs.add(("nist_sp", identifier))
    return refs


def _standard_doc_label_references(value: Any) -> set[tuple[str, str]]:
    normalized = _normalize_evidence_identity(value)
    refs: set[tuple[str, str]] = set()
    match = re.fullmatch(r"rfc\s*(\d+[a-z0-9]*)", normalized)
    if match:
        refs.add(("rfc", match.group(1)))
    match = re.fullmatch(
        r"nist\s+sp\s+(\d+(?:\s+\d+[a-z0-9]*)?)(?:\s+(?:part|pt)\s+(\d+))?(?:\s+rev\s+(\d+))?",
        normalized,
    )
    if match:
        identifier = " ".join(part for part in match.groups() if part).strip()
        if identifier:
            refs.add(("nist_sp", identifier))
    return refs


def _citation_entry_standard_doc_references(entry: dict[str, Any]) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for field in ("key", "title", "booktitle", "venue", "journal", "url", "doi", "howpublished"):
        refs.update(_standard_doc_references(entry.get(field)))
    return refs


def _standard_doc_prefixed_title_matches_entry(
    *,
    evidence_title: str,
    entry_title: str,
    entry_refs: set[tuple[str, str]],
) -> bool:
    if not evidence_title or not entry_refs:
        return False
    if entry_title and evidence_title.endswith(entry_title):
        prefix = evidence_title[: -len(entry_title)].strip()
        if _standard_doc_label_references(prefix) & entry_refs:
            return True
    return False
