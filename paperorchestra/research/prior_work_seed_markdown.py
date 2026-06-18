from __future__ import annotations

import re
from typing import Any

from paperorchestra.research.prior_work_seed_dates import _coerce_year
from paperorchestra.research.prior_work_seed_external_ids import _entry_external_ids, _normalize_doi


def _parse_markdown_seed(text: str, *, default_source: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            continue
        item = stripped.lstrip("-* ").strip()
        if not item:
            continue
        title, url = _markdown_seed_title_and_url(item)
        if len(title) < 4:
            continue
        year = _coerce_year(item)
        entries.append(
            {
                "title": title,
                "authors": [],
                "year": year,
                "publication_date": f"{year}-01-01" if year else None,
                "venue": None,
                "abstract": f"Curated prior-work seed imported from markdown line: {item}",
                "citation_count": None,
                "external_ids": _entry_external_ids({"doi": _normalize_doi(item)}),
                "url": url,
                "source": default_source,
                "provenance_notes": [item],
            }
        )
    return entries


def _markdown_seed_title_and_url(item: str) -> tuple[str, str | None]:
    link_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", item)
    if link_match:
        title = link_match.group(1).strip()
        url = link_match.group(2).strip()
    else:
        title = re.split(r"\s+[—–-]\s+|\s+\|\s+", item, maxsplit=1)[0].strip()
        url = None
    return re.sub(r"^\d+\.\s*", "", title).strip(" ."), url
