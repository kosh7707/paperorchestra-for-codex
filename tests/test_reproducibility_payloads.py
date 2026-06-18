from __future__ import annotations

from paperorchestra.reviews import reproducibility_payloads


def test_verified_paper_payload_validator_accepts_realistic_registry_entry() -> None:
    assert reproducibility_payloads._is_valid_verified_paper_payload(
        {
            "paper_id": "paper-1",
            "title": "A Useful Paper",
            "year": 2024,
            "publication_date": "2024-01-01",
            "venue": "Venue",
            "abstract": "Abstract",
            "authors": ["Ada", "Grace"],
            "citation_count": 10,
            "external_ids": {"DOI": "10.1000/example", "CorpusId": 123},
            "url": "https://example.test/paper",
            "bibtex_key": "Useful2024",
            "alias_bibtex_keys": ["Useful"],
            "origin": "macro_candidates",
            "matched_query": "query",
            "title_match_ratio": 0.9,
            "is_after_cutoff": False,
        }
    )


def test_verified_paper_payload_validator_rejects_empty_key_and_bool_counts() -> None:
    assert not reproducibility_payloads._is_valid_verified_paper_payload(
        {
            "paper_id": "paper-1",
            "title": "A Useful Paper",
            "year": True,
            "abstract": "Abstract",
            "authors": ["Ada"],
            "citation_count": 1,
            "bibtex_key": "Useful2024",
        }
    )
    assert not reproducibility_payloads._is_valid_verified_paper_payload(
        {
            "paper_id": "paper-1",
            "title": "A Useful Paper",
            "year": 2024,
            "abstract": "Abstract",
            "authors": ["Ada"],
            "citation_count": 1,
            "bibtex_key": " ",
        }
    )


def test_citation_map_entry_validator_accepts_provenance_payload() -> None:
    assert reproducibility_payloads._is_valid_citation_map_entry(
        "Useful2024",
        {
            "title": "A Useful Paper",
            "abstract": "Abstract",
            "authors": ["Ada"],
            "year": 2024,
            "venue": "Venue",
            "paper_id": "paper-1",
            "origin": "manual_seed",
            "matched_query": "query",
            "provenance": {"source": "manual"},
        },
    )


def test_citation_map_entry_validator_rejects_bad_key_author_and_provenance() -> None:
    valid_entry = {"title": "A Useful Paper", "authors": ["Ada"], "year": 2024}
    assert not reproducibility_payloads._is_valid_citation_map_entry("", valid_entry)
    assert not reproducibility_payloads._is_valid_citation_map_entry(
        "Useful2024",
        {"title": "A Useful Paper", "authors": ["Ada", 5], "year": 2024},
    )
    assert not reproducibility_payloads._is_valid_citation_map_entry(
        "Useful2024",
        {"title": "A Useful Paper", "authors": ["Ada"], "year": 2024, "provenance": "manual"},
    )
