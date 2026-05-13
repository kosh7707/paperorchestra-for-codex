from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_materials import build_material_inventory, build_source_digest
from paperorchestra.orchestrator import inspect_state


class OrchestraMaterialsTests(unittest.TestCase):
    def test_inventory_classifies_generic_files_into_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.tex").write_text("\\section{Synthetic}\n", encoding="utf-8")
            (root / "references.bib").write_text("@article{synthetic2026}\n", encoding="utf-8")
            (root / "notes.md").write_text("synthetic notes\n", encoding="utf-8")
            (root / "supplied_architecture_diagram.pdf").write_bytes(b"pdf bytes")
            inventory = build_material_inventory(root)

        self.assertEqual(inventory.file_count, 4)
        self.assertEqual(inventory.role_counts["manuscript_tex"], 1)
        self.assertEqual(inventory.role_counts["bibtex"], 1)
        self.assertEqual(inventory.role_counts["idea_or_notes"], 1)
        self.assertEqual(inventory.role_counts["figure_asset"], 1)

    def test_inventory_records_hashes_and_counts_without_raw_content(self) -> None:
        raw_marker = "SYNTHETIC_PRIVATE_CONTENT_SHOULD_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes.md").write_text(raw_marker, encoding="utf-8")
            inventory = build_material_inventory(root)
            rendered = json.dumps(inventory.to_public_dict(), ensure_ascii=False)

        self.assertNotIn(raw_marker, rendered)
        self.assertEqual(len(inventory.files[0].sha256), 64)
        self.assertTrue(inventory.private_safe_summary)

    def test_source_digest_marks_sufficient_material_for_manuscript_bib_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.tex").write_text("\\section{Synthetic}\n", encoding="utf-8")
            (root / "references.bib").write_text("@article{synthetic2026}\n", encoding="utf-8")
            (root / "notes.md").write_text("synthetic notes\n", encoding="utf-8")
            digest = build_source_digest(build_material_inventory(root))

        self.assertTrue(digest.sufficient)
        self.assertEqual(digest.status, "ready")
        self.assertTrue(digest.private_safe_summary)

    def test_source_digest_marks_single_tiny_note_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.md").write_text("tiny\n", encoding="utf-8")
            digest = build_source_digest(build_material_inventory(root))

        self.assertFalse(digest.sufficient)
        self.assertEqual(digest.status, "insufficient")

    def test_inspect_state_sets_sufficient_material_and_ready_digest_for_synthetic_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "main.tex").write_text("\\section{Synthetic}\n", encoding="utf-8")
            (material / "references.bib").write_text("@article{synthetic2026}\n", encoding="utf-8")
            (material / "notes.md").write_text("synthetic notes\n", encoding="utf-8")
            state = inspect_state(root, material_path=material)

        self.assertEqual(state.facets.material, "inventoried_sufficient")
        self.assertEqual(state.facets.source_digest, "ready")
        self.assertEqual(state.next_actions[0].action_type, "build_claim_graph")

    def test_insufficient_material_keeps_drafting_blocked_with_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "note.md").write_text("tiny\n", encoding="utf-8")
            state = inspect_state(root, material_path=material)

        self.assertEqual(state.facets.material, "inventoried_insufficient")
        self.assertNotEqual(state.facets.writing, "drafting_allowed")
        self.assertIn(state.next_actions[0].action_type, {"provide_material", "inspect_material", "block"})
        self.assertIn("insufficient_material", state.blocking_reasons)


if __name__ == "__main__":
    unittest.main()
