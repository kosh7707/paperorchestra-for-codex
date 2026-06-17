from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path


def _prior_work_metadata_rejection_reasons(entry: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    unknown_values = {"", "unknown", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}

    def is_unknown(value: Any) -> bool:
        normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
        return normalized in unknown_values

    if is_unknown(entry.get("title")):
        reasons.append("missing_title")
    authors = [author for author in entry.get("authors", []) if not is_unknown(author)]
    if not authors:
        reasons.append("missing_author_or_organization")
    if not isinstance(entry.get("year"), int):
        reasons.append("missing_year")
    elif entry.get("year_source") not in {"year", "publication_year"}:
        reasons.append("missing_explicit_year")
    return reasons


def _filter_prior_work_entries_for_complete_metadata(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        reasons = _prior_work_metadata_rejection_reasons(entry)
        if not reasons:
            kept.append(entry)
            continue
        rejected.append(
            {
                "index": index,
                "title": str(entry.get("title") or "").strip() or None,
                "source": str(entry.get("source") or "").strip() or None,
                "reasons": reasons,
                "has_publication_date": bool(str(entry.get("publication_date") or "").strip()),
            }
        )
    return kept, rejected


def _write_prior_work_import_rejection_report(
    cwd: str | Path | None,
    *,
    seed_file: str | Path,
    source: str,
    original_count: int,
    kept_count: int,
    rejected: list[dict[str, Any]],
    require_complete_metadata: bool,
) -> Path:
    path = artifact_path(cwd, "prior_work_import_rejections.json")
    reason_counts: dict[str, int] = {}
    for item in rejected:
        for reason in item.get("reasons", []):
            if isinstance(reason, str):
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
    write_json(
        path,
        {
            "schema_version": "prior-work-import-rejections/1",
            "seed_file": str(seed_file),
            "source": source,
            "require_complete_metadata": require_complete_metadata,
            "policy": {
                "required_fields": ["title", "author_or_organization", "year"],
                "all_rejected_behavior": "fail_import_and_leave_existing_registry_unchanged",
                "publication_date_without_year": "rejected_until_a_concrete_year_is_provided",
            },
            "input_entry_count": original_count,
            "accepted_entry_count": kept_count,
            "rejected_entry_count": len(rejected),
            "reason_counts": reason_counts,
            "rejected_entries": rejected,
        },
    )
    return path
