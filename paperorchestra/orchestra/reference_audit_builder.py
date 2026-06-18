from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.orchestra.reference_discovery import _redacted_seed_label, _relative_label, _seed_files, _sha256_text
from paperorchestra.orchestra.reference_fields import _fields_present, _unknown_fields
from paperorchestra.orchestra.reference_models import ReferenceMetadataAudit, ReferenceMetadataEntry
from paperorchestra.research.prior_work_seed import load_prior_work_seed


def build_reference_metadata_audit(material_path: str | Path) -> ReferenceMetadataAudit:
    root = Path(material_path).resolve()
    seed_files = _seed_files(root)
    entries, parse_failures = _reference_entries(seed_files, root)
    failing = _reference_audit_failures(seed_files=seed_files, entries=entries, parse_failures=parse_failures)
    return ReferenceMetadataAudit(
        schema_version="reference-metadata-audit/1",
        status="fail" if failing else "pass",
        seed_file_count=len(seed_files),
        entry_count=len(entries),
        unknown_entry_count=sum(1 for entry in entries if entry.unknown_fields),
        entries=entries,
        failing_codes=failing,
        seed_file_labels=[_redacted_seed_label(path, root) for path in seed_files],
        private_safe_summary=True,
    )


def _reference_entries(seed_files: list[Path], root: Path) -> tuple[list[ReferenceMetadataEntry], int]:
    entries: list[ReferenceMetadataEntry] = []
    parse_failures = 0
    for seed_file in seed_files:
        try:
            parsed = load_prior_work_seed(seed_file, source="material_seed")
        except Exception:
            parse_failures += 1
            continue
        entries.extend(_entries_for_seed(seed_file, root, parsed))
    return entries, parse_failures


def _entries_for_seed(seed_file: Path, root: Path, parsed: list[dict[str, Any]]) -> list[ReferenceMetadataEntry]:
    source_hash = _sha256_text(_relative_label(seed_file, root))
    source_label = f"redacted-reference-seed:{source_hash[:12]}"
    entries: list[ReferenceMetadataEntry] = []
    for index, item in enumerate(parsed, start=1):
        key = str(item.get("bibtex_key") or f"entry-{index}").strip() or f"entry-{index}"
        key_hash = _sha256_text(key)
        entries.append(
            ReferenceMetadataEntry(
                key_label=f"redacted-reference:{key_hash[:12]}",
                key_sha256=key_hash,
                source_label=source_label,
                source_sha256=source_hash,
                fields_present=_fields_present(item),
                unknown_fields=_unknown_fields(item),
            )
        )
    return entries


def _reference_audit_failures(
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
