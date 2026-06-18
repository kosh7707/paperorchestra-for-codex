from __future__ import annotations

from paperorchestra.core.models import VerifiedPaper
from paperorchestra.research.bibtex_citable import _metadata_unknownish, is_citable_paper
from paperorchestra.research.bibtex_values import _escape_bibtex_value


def _render_bibtex_entry(paper: VerifiedPaper, *, entry_type: str, venue_field: str, venue_value: str | None, authors: str) -> str:
    lines = [
        f"@{entry_type}{{{paper.bibtex_key},",
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


def registry_to_bibtex(registry: list[VerifiedPaper]) -> str:
    entries = []
    for paper in registry:
        if not paper.bibtex_key or not is_citable_paper(paper):
            continue
        authors = " and ".join(author for author in paper.authors if not _metadata_unknownish(author))
        is_journal = bool(paper.venue and any(token in paper.venue.lower() for token in ["journal", "transactions"]))
        entries.append(
            _render_bibtex_entry(
                paper,
                entry_type="article" if is_journal else "inproceedings",
                venue_field="journal" if is_journal else "booktitle",
                venue_value=paper.venue if not _metadata_unknownish(paper.venue) else None,
                authors=authors,
            )
        )
    return "\n\n".join(entries) + ("\n" if entries else "")
