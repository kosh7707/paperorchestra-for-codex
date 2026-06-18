from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.loop_engine.quality.citation_gap import _citation_support_gap_classification
from paperorchestra.loop_engine.quality.citation_gap_items import citation_support_gap_items


class QualityCitationGapTest(unittest.TestCase):
    def test_gap_classification_counts_machine_solvable_item_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "citation_support.json"
            path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "support_status": "weakly_supported",
                                "suggested_fix": "Narrow the claim.",
                                "citation_keys": ["x"],
                                "citation_entries": [{"key": "x", "title": "Known Source"}],
                                "evidence": [
                                    {
                                        "citation_key": "x",
                                        "source_title": "Known Source",
                                        "evidence_quote_or_summary": "Evidence text.",
                                        "supports_claim": True,
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = _citation_support_gap_classification({"path": str(path)})

        self.assertEqual(result["machine_solvable_count"], 1)
        self.assertEqual(result["manual_author_judgment_count"], 0)

    def test_v3_gap_classification_counts_verified_resolution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "citation_support_v3.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "citation-support-review/3",
                        "cases": [
                            {
                                "id": "case-1",
                                "key": "paper2026",
                                "verdict": "weak",
                                "source": {"title": "Known Source", "url": "https://example.test/paper"},
                                "suggested_fix": "Narrow the comparison.",
                                "resolution": {
                                    "support_evidence": [
                                        {
                                            "source_title": "Known Source",
                                            "evidence_quote_or_summary": "Verified supporting text.",
                                            "supports": True,
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = _citation_support_gap_classification({"path": str(path)})

        self.assertEqual(result["machine_solvable_count"], 1)
        self.assertEqual(result["payload_unavailable"], False)

    def test_v3_empty_payload_is_available_without_author_judgment_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "citation_support_v3.json"
            path.write_text(json.dumps({"schema": "citation-support-review/3", "cases": []}), encoding="utf-8")

            result = _citation_support_gap_classification({"path": str(path)})

        self.assertEqual(result["manual_author_judgment_count"], 0)
        self.assertEqual(result["payload_unavailable"], False)

    def test_v3_gap_items_project_case_metadata_and_evidence(self) -> None:
        items, v3_payload = citation_support_gap_items(
            {
                "schema": "citation-support-review/3",
                "cases": [
                    {
                        "id": "C1",
                        "key": "smith2024",
                        "verdict": "human_needed",
                        "source": {"title": "Smith Paper", "url": "https://example.test"},
                        "requires_author_judgment": True,
                        "support_evidence": [{"title": "Smith Paper", "summary": "Evidence summary.", "supports": True}],
                    },
                    {"id": "C2", "key": "ignored", "verdict": "pass"},
                    {"id": "C3", "verdict": "weak"},
                ],
            }
        )

        self.assertTrue(v3_payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["case_id"], "C1")
        self.assertEqual(items[0]["citation_keys"], ["smith2024"])
        self.assertEqual(items[0]["support_status"], "needs_manual_check")
        self.assertTrue(items[0]["requires_author_judgment"])
        self.assertEqual(items[0]["evidence"][0]["supports_claim"], True)


if __name__ == "__main__":
    unittest.main()
