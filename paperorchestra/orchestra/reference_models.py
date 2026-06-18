from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
