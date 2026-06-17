from __future__ import annotations

import datetime as dt


def parse_cutoff(cutoff_date: str | None) -> dt.date | None:
    if not cutoff_date:
        return None
    return dt.date.fromisoformat(cutoff_date)


def parse_publication_date(publication_date: str | None) -> dt.date | None:
    if not publication_date:
        return None
    return dt.date.fromisoformat(publication_date[:10])


def year_month_passes_cutoff(year: int | None, cutoff_date: str | None, publication_date: str | None = None) -> bool:
    cutoff = parse_cutoff(cutoff_date)
    if cutoff is None or year is None:
        return True
    parsed_publication_date = parse_publication_date(publication_date)
    if parsed_publication_date is not None:
        return parsed_publication_date < cutoff
    if year < cutoff.year:
        return True
    if year > cutoff.year:
        return False
    return cutoff.month == 12 and cutoff.day == 31
