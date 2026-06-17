from __future__ import annotations

import unittest

from paperorchestra.reviews.citation_source_payload import _source_type_for_entry


class CitationSourcePayloadTest(unittest.TestCase):
    def test_source_type_detects_github_repository_from_url(self) -> None:
        self.assertEqual(_source_type_for_entry({"url": "https://github.com/example/project"}), "repo")

    def test_source_type_detects_arxiv_preprint(self) -> None:
        self.assertEqual(_source_type_for_entry({"url": "https://arxiv.org/abs/1234.5678"}), "preprint")


if __name__ == "__main__":
    unittest.main()
