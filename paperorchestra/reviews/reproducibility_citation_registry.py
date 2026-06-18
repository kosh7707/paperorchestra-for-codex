from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.reviews.reproducibility_citation_entries import _registry_entry_is_mock
from paperorchestra.reviews.reproducibility_citation_registry_summary import (
    _citation_registry_provenance_from_entries,
    _cited_keys_from_paper,
    _empty_registry_provenance,
)


def _load_registry_entries(registry_path: str | Path | None) -> tuple[str | None, list[dict[str, Any]]]:
    if not registry_path:
        return "missing", []
    candidate = Path(registry_path)
    if not candidate.exists():
        return "missing", []
    try:
        payload = read_json(candidate)
    except Exception:
        return "unreadable", []
    if not isinstance(payload, list):
        return "malformed", []
    return None, [item for item in payload if isinstance(item, dict)]


def _mock_registry_entry_count(registry_path: str | Path | None) -> int:
    status, entries = _load_registry_entries(registry_path)
    if status:
        return 0
    return sum(1 for item in entries if _registry_entry_is_mock(item))


def _citation_registry_live_provenance(
    registry_path: str | Path | None,
    paper_path: str | Path | None = None,
) -> dict[str, Any]:
    status, entries = _load_registry_entries(registry_path)
    if status:
        return _empty_registry_provenance(status)
    cited_keys = _cited_keys_from_paper(paper_path)
    return _citation_registry_provenance_from_entries(entries, cited_keys)
