from __future__ import annotations

import re

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.matching import normalize_title


def _safe_bibtex_key_part(text: str, *, fallback: str) -> str:
    normalized = "".join(ch for ch in normalize_title(text).title() if ch.isalnum())
    return normalized or fallback


def make_bibtex_key(paper: VerifiedPaper) -> str:
    author_source = paper.authors[0].split()[-1] if paper.authors else ""
    author = _safe_bibtex_key_part(author_source, fallback="Anon")
    year = str(paper.year or "nd")
    slug_words = normalize_title(paper.title).split()[:3]
    slug = "".join(word.capitalize() for word in slug_words if word.isalnum()) or "Paper"
    return f"{author.lower()}{year}{slug}"


def ensure_unique_bibtex_keys(registry: list[VerifiedPaper]) -> list[VerifiedPaper]:
    seen: set[str] = set()
    for paper in registry:
        base_key = paper.bibtex_key or make_bibtex_key(paper)
        candidate = base_key
        suffix = 2
        while candidate in seen:
            candidate = f"{base_key}{suffix}"
            suffix += 1
        paper.bibtex_key = candidate
        seen.add(candidate)
    return registry


_BIBTEX_ESCAPED_VALUE_CHARS = frozenset("&%_$#")


def _validate_bibtex_value(value: str, *, field: str) -> None:
    depth = 0
    trailing_backslashes = 0
    for index, ch in enumerate(value):
        if ord(ch) < 32 and ch not in "\t\n":
            raise ValueError(f"BibTeX field '{field}' contains an unsupported control character at position {index}.")
        if ch == "\\":
            trailing_backslashes += 1
            continue
        escaped = trailing_backslashes % 2 == 1
        trailing_backslashes = 0
        if ch == "{" and not escaped:
            depth += 1
        elif ch == "}" and not escaped:
            if depth == 0:
                raise ValueError(f"BibTeX field '{field}' contains an unmatched closing brace.")
            depth -= 1
    if depth:
        raise ValueError(f"BibTeX field '{field}' contains unbalanced braces.")
    if trailing_backslashes % 2 == 1:
        raise ValueError(f"BibTeX field '{field}' ends with a dangling backslash.")


def _escape_bibtex_value(value: str, *, field: str) -> str:
    _validate_bibtex_value(value, field=field)
    escaped: list[str] = []
    trailing_backslashes = 0
    for ch in value:
        if ch == "\\":
            escaped.append(ch)
            trailing_backslashes += 1
            continue
        is_escaped = trailing_backslashes % 2 == 1
        trailing_backslashes = 0
        if ch in _BIBTEX_ESCAPED_VALUE_CHARS and not is_escaped:
            escaped.append("\\")
        escaped.append(ch)
    return "".join(escaped)


_UNKNOWN_METADATA_VALUES = {"", "unknown", "unknown venue", "n/a", "na", "none", "null", "tbd", "todo", "anonymous"}


def _metadata_unknownish(value: object) -> bool:
    normalized = re.sub(r"\s+", " ", str(value or "").strip()).lower()
    return normalized in _UNKNOWN_METADATA_VALUES


def paper_citable_metadata_failures(paper: VerifiedPaper) -> list[str]:
    """Return reasons a registry entry must not be exposed as citable.

    A missing citation is safer than a bibliography entry rendered with
    ``Unknown`` placeholders.  Keep incomplete entries in the registry for
    diagnostics/repair, but exclude them from ``references.bib`` and
    ``citation_map.json`` until enough metadata is available to make the source
    traceable by a reader.
    """

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


def registry_to_bibtex(registry: list[VerifiedPaper]) -> str:
    entries = []
    for paper in registry:
        if not is_citable_paper(paper):
            continue
        authors = " and ".join(author for author in paper.authors if not _metadata_unknownish(author))
        is_journal = bool(paper.venue and any(token in paper.venue.lower() for token in ["journal", "transactions"]))
        entry_type = "article" if is_journal else "inproceedings"
        venue_field = "journal" if is_journal else "booktitle"
        venue_value = paper.venue if not _metadata_unknownish(paper.venue) else None

        def render_entry(bibtex_key: str) -> str:
            lines = [
                f"@{entry_type}{{{bibtex_key},",
                f"  title = {{{_escape_bibtex_value(paper.title, field='title')}}},",
                f"  year = {{{_escape_bibtex_value(str(paper.year or ''), field='year')}}},",
            ]
            if authors:
                lines.append(f"  author = {{{_escape_bibtex_value(authors, field='author')}}},")
            if venue_value:
                lines.append(f"  {venue_field} = {{{_escape_bibtex_value(venue_value, field=venue_field)}}},")
            if paper.url:
                lines.append(f"  url = {{{_escape_bibtex_value(paper.url, field='url')}}},")
            if paper.external_ids.get("DOI"):
                lines.append(f"  doi = {{{_escape_bibtex_value(paper.external_ids['DOI'], field='doi')}}},")
            lines.append("}")
            return "\n".join(lines)

        if paper.bibtex_key:
            entries.append(render_entry(paper.bibtex_key))
    return "\n\n".join(entries) + ("\n" if entries else "")
