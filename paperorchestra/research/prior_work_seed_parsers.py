from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.research.prior_work_seed_bibtex import _extract_bibtex_field, _parse_bibtex_seed
from paperorchestra.research.prior_work_seed_json import _parse_json_seed
from paperorchestra.research.prior_work_seed_markdown import _parse_markdown_seed
from paperorchestra.research.prior_work_seed_normalization import (
    _coerce_year,
    _entry_external_ids,
    _normalize_doi,
    _normalize_seed_entry,
    _split_authors,
)


def load_prior_work_seed(path: str | Path, *, source: str = "manual_seed") -> list[dict[str, Any]]:
    seed_path = Path(path)
    text = seed_path.read_text(encoding="utf-8")
    suffix = seed_path.suffix.lower()
    if suffix == ".json":
        return _parse_json_seed(text, default_source=source)
    if suffix in {".bib", ".bibtex"} or text.lstrip().startswith("@"):
        return _parse_bibtex_seed(text, default_source=source)
    return _parse_markdown_seed(text, default_source=source)
