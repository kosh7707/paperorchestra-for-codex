from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .literature import load_prior_work_seed

REFERENCE_SEED_EXTENSIONS = {".bib", ".bibtex"}
UNKNOWN_VALUES = {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


@dataclass(frozen=True)
class ReferenceMetadataEntry:
    key_label: str
    key_sha256: str
    source_label: str
    source_sha256: str
    fields_present: list[str]
    unknown_fields: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "key_label": self.key_label,
            "key_sha256": self.key_sha256,
            "source_label": self.source_label,
            "source_sha256": self.source_sha256,
            "fields_present": list(self.fields_present),
            "unknown_fields": list(self.unknown_fields),
        }


@dataclass(frozen=True)
class ReferenceMetadataAudit:
    schema_version: str
    status: str
    seed_file_count: int
    entry_count: int
    unknown_entry_count: int
    entries: list[ReferenceMetadataEntry] = field(default_factory=list)
    failing_codes: list[str] = field(default_factory=list)
    seed_file_labels: list[str] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "seed_file_count": self.seed_file_count,
            "entry_count": self.entry_count,
            "unknown_entry_count": self.unknown_entry_count,
            "entries": [entry.to_public_dict() for entry in self.entries],
            "failing_codes": list(self.failing_codes),
            "seed_file_labels": list(self.seed_file_labels),
            "private_safe_summary": self.private_safe_summary,
        }


def build_reference_metadata_audit(material_path: str | Path) -> ReferenceMetadataAudit:
    root = Path(material_path).resolve()
    seed_files = _seed_files(root)
    seed_labels = [f"redacted-reference-seed:{_sha256_text(_relative_label(path, root))[:12]}" for path in seed_files]
    entries: list[ReferenceMetadataEntry] = []
    failing: list[str] = []
    parse_failures = 0
    for seed_file in seed_files:
        source_hash = _sha256_text(_relative_label(seed_file, root))
        source_label = f"redacted-reference-seed:{source_hash[:12]}"
        try:
            parsed = load_prior_work_seed(seed_file, source="material_seed")
        except Exception:
            parse_failures += 1
            continue
        for index, item in enumerate(parsed, start=1):
            key = str(item.get("bibtex_key") or f"entry-{index}").strip() or f"entry-{index}"
            key_hash = _sha256_text(key)
            fields_present = _fields_present(item)
            unknown_fields = _unknown_fields(item)
            entries.append(
                ReferenceMetadataEntry(
                    key_label=f"redacted-reference:{key_hash[:12]}",
                    key_sha256=key_hash,
                    source_label=source_label,
                    source_sha256=source_hash,
                    fields_present=fields_present,
                    unknown_fields=unknown_fields,
                )
            )
    if not seed_files:
        failing.append("reference_metadata_seed_missing")
    if seed_files and not entries:
        failing.append("reference_metadata_entries_missing")
    if parse_failures:
        failing.append("reference_metadata_parse_failed")
    if any(entry.unknown_fields for entry in entries):
        failing.append("reference_metadata_unknown_fields")
    failing = sorted(dict.fromkeys(failing))
    return ReferenceMetadataAudit(
        schema_version="reference-metadata-audit/1",
        status="fail" if failing else "pass",
        seed_file_count=len(seed_files),
        entry_count=len(entries),
        unknown_entry_count=sum(1 for entry in entries if entry.unknown_fields),
        entries=entries,
        failing_codes=failing,
        seed_file_labels=seed_labels,
        private_safe_summary=True,
    )


def _seed_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in REFERENCE_SEED_EXTENSIONS else []
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in REFERENCE_SEED_EXTENSIONS)


def _relative_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)) if root.is_dir() else path.name
    except ValueError:
        return path.name


def _fields_present(item: dict[str, Any]) -> list[str]:
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


def _unknown_fields(item: dict[str, Any]) -> list[str]:
    unknown: list[str] = []
    if _unknown_value(str(item.get("title") or "")):
        unknown.append("title")
    authors = item.get("authors") if isinstance(item.get("authors"), list) else []
    if not authors or all(_unknown_value(str(author)) for author in authors):
        unknown.append("author")
    if item.get("year") is None:
        unknown.append("year")
    return unknown


def _unknown_value(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip()).lower()
    return normalized in UNKNOWN_VALUES


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
