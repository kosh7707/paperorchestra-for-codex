from __future__ import annotations

import unittest

from paperorchestra.reviews.citation_source_payload import _lean_source_payload, _source_type_for_entry


class CitationSourcePayloadTest(unittest.TestCase):
    def test_source_type_detects_github_repository_from_url(self) -> None:
        self.assertEqual(_source_type_for_entry({"url": "https://github.com/example/project"}), "repo")

    def test_source_type_detects_arxiv_preprint(self) -> None:
        self.assertEqual(_source_type_for_entry({"url": "https://arxiv.org/abs/1234.5678"}), "preprint")

    def test_source_type_detects_non_paper_sources_from_text_and_url(self) -> None:
        self.assertEqual(_source_type_for_entry({"venue": "NIST Standard"}), "standard")
        self.assertEqual(_source_type_for_entry({"journal": "Technical Report"}), "report")
        self.assertEqual(_source_type_for_entry({"url": "https://zenodo.org/records/1"}), "dataset")
        self.assertEqual(_source_type_for_entry({"venue": "Blog Post"}), "blog")
        self.assertEqual(_source_type_for_entry({"venue": "Documentation Manual"}), "docs")
        self.assertEqual(_source_type_for_entry({"title": "Regular Paper"}), "paper")
        self.assertEqual(_source_type_for_entry({}), "other")

    def test_lean_source_payload_prefers_real_entry_fields_and_defaults_title(self) -> None:
        payload = _lean_source_payload(
            "KeyA",
            {
                "KeyA": {
                    "title": "A Paper",
                    "source_url": "https://example.test/source",
                    "DOI": "10/example",
                    "ArXiv": "1234.5678",
                    "venue": "arXiv preprint",
                }
            },
        )
        missing = _lean_source_payload("Missing", {})

        self.assertEqual(
            payload,
            {
                "type": "preprint",
                "title": "A Paper",
                "url": "https://example.test/source",
                "doi": "10/example",
                "arxiv": "1234.5678",
            },
        )
        self.assertEqual(missing, {"type": "other", "title": "Missing"})


if __name__ == "__main__":
    unittest.main()
