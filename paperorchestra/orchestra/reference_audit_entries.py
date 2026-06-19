from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from paperorchestra.orchestra.reference_audit_models import ReferenceMetadataEntry
from paperorchestra.research.prior_work_seed_parsers import load_prior_work_seed

REFERENCE_SEED_EXTENSIONS = {".bib", ".bibtex"}
UNKNOWN_VALUES = {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def seed_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in REFERENCE_SEED_EXTENSIONS else []
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in REFERENCE_SEED_EXTENSIONS)


def reference_entries(seed_paths: list[Path], root: Path) -> tuple[list[ReferenceMetadataEntry], int]:
    entries: list[ReferenceMetadataEntry] = []
    parse_failures = 0
    for seed_file in seed_paths:
        try:
            parsed = load_prior_work_seed(seed_file, source="material_seed")
        except Exception:
            parse_failures += 1
            continue
        entries.extend(entries_for_seed(seed_file, root, parsed))
    return entries, parse_failures


def entries_for_seed(seed_file: Path, root: Path, parsed: list[dict[str, Any]]) -> list[ReferenceMetadataEntry]:
    source_hash = sha256_text(relative_label(seed_file, root))
    source_label = f"redacted-reference-seed:{source_hash[:12]}"
    entries: list[ReferenceMetadataEntry] = []
    for index, item in enumerate(parsed, start=1):
        key = str(item.get("bibtex_key") or f"entry-{index}").strip() or f"entry-{index}"
        key_hash = sha256_text(key)
        entries.append(
            ReferenceMetadataEntry(
                key_label=f"redacted-reference:{key_hash[:12]}",
                key_sha256=key_hash,
                source_label=source_label,
                source_sha256=source_hash,
                fields_present=fields_present(item),
                unknown_fields=unknown_fields(item),
            )
        )
    return entries


def fields_present(item: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    if str(item.get("title") or "").strip():
        fields.append("title")
    if item.get("authors"):
        fields.append("author")
    if item.get("year") is not None:
        fields.append("year")
    if str(item.get("venue") or "").strip():
        fields.append("venue")
    if str(item.get("url") or "").strip():
        fields.append("url")
    external = item.get("external_ids") if isinstance(item.get("external_ids"), dict) else {}
    if external:
        fields.append("external_ids")
    return fields


def unknown_fields(item: dict[str, Any]) -> list[str]:
    unknown: list[str] = []
    if unknown_value(str(item.get("title") or "")):
        unknown.append("title")
    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
    if not authors or all(unknown_value(str(author)) for author in authors):
        unknown.append("author")
    if item.get("year") is None:
        unknown.append("year")
    return unknown


def unknown_value(value: str) -> bool:
    return re.sub(r"\s+", " ", value.strip()).lower() in UNKNOWN_VALUES


def relative_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)) if root.is_dir() else path.name
    except ValueError:
        return path.name


def redacted_seed_label(path: Path, root: Path) -> str:
    return f"redacted-reference-seed:{sha256_text(relative_label(path, root))[:12]}"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


__all__ = [
    "REFERENCE_SEED_EXTENSIONS",
    "UNKNOWN_VALUES",
    "fields_present",
    "redacted_seed_label",
    "reference_entries",
    "seed_files",
    "sha256_text",
    "unknown_fields",
    "unknown_value",
]
