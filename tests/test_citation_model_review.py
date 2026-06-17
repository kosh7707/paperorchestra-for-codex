from __future__ import annotations

import unittest

from paperorchestra.reviews.citation_model_review import _heuristic_citation_items


class CitationModelReviewTest(unittest.TestCase):
    def test_heuristic_items_extract_cited_sentence_support_payload(self) -> None:
        latex = r"Prior tools discuss alert triage in practice~\cite{toolpaper}."
        citation_map = {
            "toolpaper": {
                "title": "Alert Triage in Practice",
                "authors": ["A. Researcher"],
                "year": 2024,
                "venue": "SEC",
                "url": "https://example.test/toolpaper",
            }
        }

        items = _heuristic_citation_items(latex, citation_map)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["citation_keys"], ["toolpaper"])
        self.assertEqual(items[0]["citation_entries"][0]["title"], "Alert Triage in Practice")


if __name__ == "__main__":
    unittest.main()
