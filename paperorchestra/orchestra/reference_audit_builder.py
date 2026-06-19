from __future__ import annotations

from pathlib import Path

from paperorchestra.orchestra.reference_audit_entries import redacted_seed_label, reference_entries, seed_files
from paperorchestra.orchestra.reference_audit_models import ReferenceMetadataAudit, ReferenceMetadataEntry


def build_reference_metadata_audit(material_path: str | Path) -> ReferenceMetadataAudit:
    root = Path(material_path).resolve()
    seeds = seed_files(root)
    entries, parse_failures = reference_entries(seeds, root)
    failing = reference_audit_failures(seed_files=seeds, entries=entries, parse_failures=parse_failures)
    return ReferenceMetadataAudit(
        schema_version="reference-metadata-audit/1",
        status="fail" if failing else "pass",
        seed_file_count=len(seeds),
        entry_count=len(entries),
        unknown_entry_count=sum(1 for entry in entries if entry.unknown_fields),
        entries=entries,
        failing_codes=failing,
        seed_file_labels=[redacted_seed_label(path, root) for path in seeds],
        private_safe_summary=True,
    )


def reference_audit_failures(
    *,
    seed_files: list[Path],
    entries: list[ReferenceMetadataEntry],
    parse_failures: int,
) -> list[str]:
    failing: list[str] = []
    if not seed_files:
        failing.append("reference_metadata_seed_missing")
    if seed_files and not entries:
        failing.append("reference_metadata_entries_missing")
    if parse_failures:
        failing.append("reference_metadata_parse_failed")
    if any(entry.unknown_fields for entry in entries):
        failing.append("reference_metadata_unknown_fields")
    return sorted(dict.fromkeys(failing))


_reference_audit_failures = reference_audit_failures

__all__ = ["ReferenceMetadataAudit", "ReferenceMetadataEntry", "build_reference_metadata_audit"]
