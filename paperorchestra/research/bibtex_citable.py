from __future__ import annotations

import re

from paperorchestra.core.models import VerifiedPaper

_UNKNOWN_METADATA_VALUES = {"", "unknown", "unknown venue", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def _metadata_unknownish(value: object) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return normalized in _UNKNOWN_METADATA_VALUES


def paper_citable_metadata_failures(paper: VerifiedPaper) -> list[str]:
    """Return reasons a registry entry must not be exposed as citable."""
    failures: list[str] = []
    if _metadata_unknownish(paper.title):
        failures.append("title_unknown")
    if paper.authors and all(_metadata_unknownish(author) for author in paper.authors):
        failures.append("author_or_organization_unknown")
    if paper.year is None and _metadata_unknownish(paper.publication_date):
        failures.append("year_unknown")
    return sorted(dict.fromkeys(failures))


def is_citable_paper(paper: VerifiedPaper) -> bool:
    return not paper_citable_metadata_failures(paper)
