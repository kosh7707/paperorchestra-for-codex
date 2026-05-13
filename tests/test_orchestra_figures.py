from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_figures import FigureAsset, FigureGatePolicy, FigureSlot, inventory_figure_assets
from paperorchestra.orchestra_state import OrchestraFacets, OrchestraState


class OrchestraFigureGateTests(unittest.TestCase):
    def test_figure_inventory_records_supplied_generic_assets_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "supplied_architecture_diagram.pdf"
            asset.write_bytes(b"synthetic figure bytes")
            inventory = inventory_figure_assets(tmp)

        self.assertEqual(len(inventory.assets), 1)
        self.assertEqual(inventory.assets[0].filename, "supplied_architecture_diagram.pdf")
        self.assertEqual(len(inventory.assets[0].sha256), 64)

    def test_safe_figure_slot_semantic_match_marks_slot_matched(self) -> None:
        decision = FigureGatePolicy().match_slot(
            FigureSlot(slot_id="F1", purpose="architecture diagram", placeholder=True),
            [FigureAsset(path="/tmp/supplied_architecture_diagram.pdf", filename="supplied_architecture_diagram.pdf", sha256="a" * 64)],
        )
        self.assertEqual(decision.status, "matched")
        self.assertEqual(decision.asset_filename, "supplied_architecture_diagram.pdf")

    def test_ambiguous_figure_match_records_human_finalization_blocker(self) -> None:
        decision = FigureGatePolicy().match_slot(
            FigureSlot(slot_id="F1", purpose="architecture diagram", placeholder=True),
            [FigureAsset(path="/tmp/unrelated_plot.pdf", filename="unrelated_plot.pdf", sha256="a" * 64)],
        )
        self.assertEqual(decision.status, "human_finalization_needed")
        self.assertIn("ambiguous_or_missing_figure_match", decision.reasons)

    def test_placeholder_only_figure_state_blocks_final_readiness(self) -> None:
        state = OrchestraState.new(
            cwd="/tmp/example",
            facets=OrchestraFacets(figures="placeholder_only", quality="human_finalization_candidate"),
        )
        updated = FigureGatePolicy().apply_to_state(state)

        self.assertNotEqual(updated.readiness.label, "ready_for_human_finalization")
        self.assertIn("placeholder_figure_unresolved", updated.blocking_reasons)
