from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_claims import build_claim_graph_from_materials
from paperorchestra.orchestra_materials import build_material_inventory, build_source_digest
from paperorchestra.orchestrator import run_until_blocked


class OrchestraClaimsTests(unittest.TestCase):
    def _material_dir(self, root: Path) -> Path:
        material = root / "material"
        material.mkdir()
        (material / "main.tex").write_text(
            """
            \\section{Synthetic Method}
            We propose a synthetic orchestration method for manuscript drafting.
            The method reduces review latency by 37 percent compared with a baseline workflow.
            This is a new workflow interface for coordinating evidence checks.
            Background systems can produce drafts without source-grounded obligations.
            """,
            encoding="utf-8",
        )
        (material / "references.bib").write_text("@article{synthetic2026,title={Synthetic Reference}}\n", encoding="utf-8")
        (material / "experiment_results.md").write_text(
            "The synthetic experiment reports 37 percent lower review latency.\n",
            encoding="utf-8",
        )
        return material

    def test_generic_text_signals_yield_typed_claim_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            material = self._material_dir(Path(tmp))
            inventory = build_material_inventory(material)
            report = build_claim_graph_from_materials(material, inventory, build_source_digest(inventory))

        claim_types = {claim.claim_type for claim in report.claims}
        self.assertIn("method", claim_types)
        self.assertIn("numeric", claim_types)
        self.assertIn("novelty", claim_types)
        self.assertGreaterEqual(report.claim_count, 3)

    def test_public_claim_graph_redacts_raw_claim_text(self) -> None:
        private_marker = "SYNTHETIC_PRIVATE_CLAIM_SHOULD_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "main.tex").write_text(
                f"We propose a method. The method improves latency by 12 percent. {private_marker}.\n",
                encoding="utf-8",
            )
            (material / "references.bib").write_text("@article{synthetic2026}\n", encoding="utf-8")
            inventory = build_material_inventory(material)
            report = build_claim_graph_from_materials(material, inventory, build_source_digest(inventory))
            rendered = json.dumps(report.to_public_dict(), ensure_ascii=False)

        self.assertNotIn(private_marker, rendered)
        self.assertTrue(report.private_safe_summary)
        self.assertTrue(all(claim.text_label.startswith("redacted-claim:") for claim in report.claims))
        self.assertTrue(all(len(claim.text_sha256) == 64 for claim in report.claims))

    def test_high_criticality_candidates_create_machine_solvable_obligations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            material = self._material_dir(Path(tmp))
            inventory = build_material_inventory(material)
            report = build_claim_graph_from_materials(material, inventory, build_source_digest(inventory))

        high_claim_ids = {claim.claim_id for claim in report.claims if claim.criticality == "high"}
        self.assertTrue(high_claim_ids)
        self.assertTrue(
            any(obligation.claim_id in high_claim_ids and obligation.machine_solvable for obligation in report.evidence_obligations)
        )
        self.assertTrue(any(citation.claim_id in high_claim_ids and citation.critical for citation in report.citation_obligations))

    def test_low_background_claims_do_not_route_to_human_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "notes.md").write_text(
                "Background systems can produce drafts. Prior tools exist. This note describes context.\n",
                encoding="utf-8",
            )
            (material / "guidelines.md").write_text("Use a synthetic conference format.\n", encoding="utf-8")
            inventory = build_material_inventory(material)
            report = build_claim_graph_from_materials(material, inventory, build_source_digest(inventory))

        self.assertTrue(report.claims)
        self.assertFalse(any(obligation.status == "human_needed" for obligation in report.evidence_obligations))
        self.assertFalse(any(citation.status == "human_needed" for citation in report.citation_obligations))

    def test_insufficient_material_cannot_build_ready_claim_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "note.md").write_text("tiny\n", encoding="utf-8")
            inventory = build_material_inventory(material)
            report = build_claim_graph_from_materials(material, inventory, build_source_digest(inventory))

        self.assertFalse(report.ready)
        self.assertIn("source_digest_not_ready", report.blocking_reasons)
        self.assertEqual(report.claim_count, 0)

    def test_run_until_blocked_progresses_sufficient_material_to_claim_planning_not_drafting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = self._material_dir(root)
            state = run_until_blocked(root, material_path=material)

        self.assertEqual(state.facets.material, "inventoried_sufficient")
        self.assertEqual(state.facets.source_digest, "ready")
        self.assertEqual(state.facets.claims, "candidate")
        self.assertIn(state.facets.evidence, {"research_needed", "durable_research_needed", "missing"})
        self.assertNotEqual(state.facets.writing, "drafting_allowed")
        self.assertIn("claim_graph", {ref["kind"] for ref in state.evidence_refs})
        self.assertNotIn("paper_full_tex", json.dumps(state.to_public_dict(), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
