from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.research import prior_work_seed


def test_load_prior_work_seed_parses_json_bibtex_and_markdown(tmp_path: Path) -> None:
    json_seed = tmp_path / "seed.json"
    json_seed.write_text(
        json.dumps(
            {
                "references": [
                    {
                        "title": "Sifting the Noise",
                        "authors": [{"name": "A. Author"}],
                        "year": "2024",
                        "doi": "https://doi.org/10.1145/1234567",
                        "bibtex_key": "sifting2024",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    parsed_json = prior_work_seed.load_prior_work_seed(json_seed, source="keynote")
    assert parsed_json[0]["title"] == "Sifting the Noise"
    assert parsed_json[0]["authors"] == ["A. Author"]
    assert parsed_json[0]["year"] == 2024
    assert parsed_json[0]["external_ids"]["DOI"] == "10.1145/1234567"

    bib_seed = tmp_path / "seed.bib"
    bib_seed.write_text(
        """
@inproceedings{iris2023,
  title = {IRIS: A Grounded Review System},
  author = {Ada Lovelace and Grace Hopper},
  year = {2023},
  booktitle = {Security Symposium},
  doi = {10.5555/iris}
}
""",
        encoding="utf-8",
    )
    parsed_bib = prior_work_seed.load_prior_work_seed(bib_seed, source="bib")
    assert parsed_bib[0]["title"] == "IRIS: A Grounded Review System"
    assert parsed_bib[0]["bibtex_key"] == "iris2023"
    assert parsed_bib[0]["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert parsed_bib[0]["venue"] == "Security Symposium"

    md_seed = tmp_path / "seed.md"
    md_seed.write_text("- [LLift: LLMs for Alerts](https://example.test/llift) — 2022\n", encoding="utf-8")
    parsed_md = prior_work_seed.load_prior_work_seed(md_seed, source="notes")
    assert parsed_md[0]["title"] == "LLift: LLMs for Alerts"
    assert parsed_md[0]["year"] == 2022
    assert parsed_md[0]["url"] == "https://example.test/llift"


def test_prior_work_entries_to_verified_papers_dedupes_aliases_and_applies_cutoff() -> None:
    papers = prior_work_seed.prior_work_entries_to_verified_papers(
        [
            {
                "title": "BugLens: Reviewing Static Analyzer Alerts",
                "bibtex_key": "buglens2024",
                "authors": "Kim and Lee",
                "year": 2024,
                "publication_date": "2024-06-01",
                "source": "manual",
            },
            {
                "title": "BugLens Reviewing Static Analyzer Alerts",
                "bibtex_key": "buglens_alias",
                "authors": ["Kim", "Lee"],
                "year": 2024,
                "publication_date": "2024-06-01",
                "source": "manual",
            },
            {
                "title": "Too New Paper",
                "year": 2025,
                "publication_date": "2025-01-01",
                "source": "manual",
            },
        ],
        cutoff_date="2024-12-31",
    )

    assert [paper.title for paper in papers] == ["BugLens: Reviewing Static Analyzer Alerts"]
    assert papers[0].bibtex_key == "buglens2024"
    assert papers[0].alias_bibtex_keys == ["buglens_alias"]
    assert papers[0].authors == ["Kim", "Lee"]
