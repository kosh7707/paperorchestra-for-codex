from __future__ import annotations

from paperorchestra.engine.prior_work_policy import _filter_prior_work_entries_for_complete_metadata


def test_complete_metadata_filter_keeps_only_entries_with_explicit_year_source() -> None:
    entries = [
        {
            "title": "Complete Paper",
            "authors": ["A. Author"],
            "year": 2024,
            "year_source": "year",
            "source": "manual_seed",
        },
        {
            "title": "Publication Date Only",
            "authors": ["Spec Team"],
            "publication_date": "2024-03-01",
            "year": 2024,
            "source": "manual_seed",
        },
        {"title": "Unknown Author", "authors": ["unknown"], "year": 2023, "year_source": "year"},
        {"title": "TBD", "authors": ["A. Author"], "year": None, "source": "manual_seed"},
    ]

    kept, rejected = _filter_prior_work_entries_for_complete_metadata(entries)

    assert kept == [entries[0]]
    assert rejected == [
        {
            "index": 2,
            "title": "Publication Date Only",
            "source": "manual_seed",
            "reasons": ["missing_explicit_year"],
            "has_publication_date": True,
        },
        {
            "index": 3,
            "title": "Unknown Author",
            "source": None,
            "reasons": ["missing_author_or_organization"],
            "has_publication_date": False,
        },
        {
            "index": 4,
            "title": "TBD",
            "source": "manual_seed",
            "reasons": ["missing_title", "missing_year"],
            "has_publication_date": False,
        },
    ]
