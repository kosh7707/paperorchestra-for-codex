from __future__ import annotations

import unittest

from paperorchestra.reviews.citation_evidence import citation_item_has_valid_supporting_evidence
from paperorchestra.reviews.citation_items import _heuristic_citation_items


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

    def test_valid_supporting_evidence_requires_matching_cited_source(self) -> None:
        item = {
            "citation_keys": ["toolpaper"],
            "citation_entries": [{"key": "toolpaper", "title": "Alert Triage in Practice"}],
            "evidence": [
                {
                    "citation_key": "toolpaper",
                    "source_title": "Alert Triage in Practice",
                    "evidence_quote_or_summary": "The paper discusses alert triage.",
                    "supports_claim": "yes",
                }
            ],
        }

        self.assertTrue(citation_item_has_valid_supporting_evidence(item))

        item["evidence"][0]["source_title"] = "Unrelated Source"
        self.assertFalse(citation_item_has_valid_supporting_evidence(item))


if __name__ == "__main__":
    unittest.main()
