from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_references import build_reference_metadata_audit
from paperorchestra.orchestrator import run_until_blocked


class OrchestraReferenceMetadataTests(unittest.TestCase):
    def test_bib_material_with_required_metadata_passes_with_redacted_public_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "references.bib").write_text(
                """
                @article{synthetic2026,
                  title = {Synthetic Reference Metadata},
                  author = {Ada Example and Ben Example},
                  year = {2026},
                  url = {https://example.test/synthetic}
                }
                """,
                encoding="utf-8",
            )
            audit = build_reference_metadata_audit(root)
            rendered = json.dumps(audit.to_public_dict(), ensure_ascii=False)

        self.assertEqual(audit.status, "pass")
        self.assertEqual(audit.entry_count, 1)
        self.assertEqual(audit.unknown_entry_count, 0)
        self.assertIn("redacted-reference:", rendered)
        self.assertNotIn("Synthetic Reference Metadata", rendered)
        self.assertNotIn("Ada Example", rendered)

    def test_unknown_or_missing_metadata_fields_fail_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "references.bib").write_text(
                """
                @article{unknown2026,
                  title = {Unknown},
                  author = {Anonymous},
                  year = {TODO}
                }
                """,
                encoding="utf-8",
            )
            audit = build_reference_metadata_audit(root)

        self.assertEqual(audit.status, "fail")
        self.assertIn("reference_metadata_unknown_fields", audit.failing_codes)
        self.assertEqual(audit.unknown_entry_count, 1)
        self.assertIn("title", audit.entries[0].unknown_fields)
        self.assertIn("author", audit.entries[0].unknown_fields)
        self.assertIn("year", audit.entries[0].unknown_fields)

    def test_missing_bib_seed_fails_without_fabricating_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.md").write_text("Synthetic notes without references.\n", encoding="utf-8")
            audit = build_reference_metadata_audit(root)

        self.assertEqual(audit.status, "fail")
        self.assertEqual(audit.seed_file_count, 0)
        self.assertEqual(audit.entry_count, 0)
        self.assertIn("reference_metadata_seed_missing", audit.failing_codes)

    def test_public_audit_omits_raw_private_marker_metadata(self) -> None:
        marker = "SYNTHETIC_PRIVATE_REFERENCE_TITLE_SHOULD_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "references.bib").write_text(
                f"""
                @article{{private2026,
                  title = {{{marker}}},
                  author = {{Private Author Marker}},
                  year = {{2026}}
                }}
                """,
                encoding="utf-8",
            )
            audit = build_reference_metadata_audit(root)
            rendered = json.dumps(audit.to_public_dict(), ensure_ascii=False)

        self.assertNotIn(marker, rendered)
        self.assertNotIn("Private Author Marker", rendered)
        self.assertTrue(audit.private_safe_summary)
        self.assertEqual(len(audit.entries[0].key_sha256), 64)

    def test_run_until_blocked_records_reference_metadata_audit_without_replacing_research_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "main.tex").write_text(
                "We propose a new synthetic workflow for evidence-grounded writing.\n",
                encoding="utf-8",
            )
            (material / "references.bib").write_text(
                """
                @article{unknown2026,
                  title = {Unknown},
                  author = {Anonymous},
                  year = {TODO}
                }
                """,
                encoding="utf-8",
            )
            (material / "notes.md").write_text("Synthetic notes.\n", encoding="utf-8")
            state = run_until_blocked(root, material_path=material)

        self.assertEqual(state.facets.citations, "unknown_refs")
        self.assertIn("reference_metadata_incomplete", state.blocking_reasons)
        self.assertIn("reference_metadata_audit", {ref["kind"] for ref in state.evidence_refs})
        self.assertIn(state.next_actions[0].action_type, {"start_autoresearch", "start_autoresearch_goal"})
        self.assertNotEqual(state.facets.writing, "drafting_allowed")


if __name__ == "__main__":
    unittest.main()
