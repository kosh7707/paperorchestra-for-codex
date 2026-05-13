from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_claims import (
    CitationObligation,
    ClaimCandidate,
    ClaimGraphReport,
    EvidenceObligation,
    build_claim_graph_from_materials,
)
from paperorchestra.orchestra_materials import build_material_inventory, build_source_digest
from paperorchestra.orchestra_research import build_evidence_research_mission
from paperorchestra.orchestrator import run_until_blocked


class OrchestraResearchMissionTests(unittest.TestCase):
    def _claim(self, *, claim_type: str = "numeric", raw_text: str = "Synthetic raw claim.") -> ClaimCandidate:
        return ClaimCandidate(
            claim_id="C1",
            claim_type=claim_type,
            graph_role="central_support" if claim_type != "background" else "background",
            criticality="high" if claim_type in {"numeric", "comparative", "novelty", "causal"} else "low",
            text_sha256="a" * 64,
            text_label="redacted-claim:aaaaaaaaaaaa",
            source_label="redacted-material:bbbbbbbbbbbb",
            source_sha256="b" * 64,
            raw_text=raw_text,
        )

    def _report(self, claim: ClaimCandidate) -> ClaimGraphReport:
        return ClaimGraphReport(
            schema_version="claim-graph/1",
            status="candidate",
            ready=True,
            claim_count=1,
            claims=[claim],
            evidence_obligations=[EvidenceObligation("E1", claim.claim_id, "research_needed", claim.criticality)],
            citation_obligations=[CitationObligation("R1", claim.claim_id, "unknown_reference", claim.criticality == "high")],
        )

    def test_mission_redacts_raw_claim_text_but_preserves_hashes(self) -> None:
        marker = "SYNTHETIC_PRIVATE_RESEARCH_MISSION_TEXT_SHOULD_NOT_LEAK"
        mission = build_evidence_research_mission(self._report(self._claim(raw_text=marker)))
        rendered = json.dumps(mission.to_public_dict(), ensure_ascii=False)

        self.assertNotIn(marker, rendered)
        self.assertIn("redacted-claim:aaaaaaaaaaaa", rendered)
        self.assertIn("a" * 64, rendered)
        self.assertTrue(mission.private_safe_summary)

    def test_numeric_obligation_chooses_standard_autoresearch_skill_surface(self) -> None:
        mission = build_evidence_research_mission(self._report(self._claim(claim_type="numeric")))

        self.assertEqual(mission.desired_surface, "$autoresearch")
        self.assertFalse(mission.durable_required)
        self.assertEqual(mission.execution_status, "planned_only")

    def test_novelty_obligation_chooses_durable_autoresearch_goal_surface(self) -> None:
        mission = build_evidence_research_mission(self._report(self._claim(claim_type="novelty")))

        self.assertEqual(mission.desired_surface, "$autoresearch-goal")
        self.assertTrue(mission.durable_required)

    def test_unknown_citation_support_remains_machine_solvable_not_human_needed(self) -> None:
        mission = build_evidence_research_mission(self._report(self._claim(claim_type="comparative")))

        self.assertTrue(mission.tasks)
        self.assertTrue(all(task.machine_solvable for task in mission.tasks))
        self.assertFalse(any(task.status == "human_needed" for task in mission.tasks))

    def test_public_mission_is_planned_only_and_never_deprecated_command(self) -> None:
        mission = build_evidence_research_mission(self._report(self._claim(claim_type="numeric")))
        rendered = json.dumps(mission.to_public_dict(), ensure_ascii=False)

        self.assertIn("planned_only", rendered)
        self.assertIn("$autoresearch", rendered)
        self.assertNotIn("omx autoresearch", rendered)
        self.assertNotIn("executable_command", rendered)

    def test_empty_obligation_graph_produces_ready_noop_mission(self) -> None:
        claim = self._claim(claim_type="background")
        report = ClaimGraphReport(
            schema_version="claim-graph/1",
            status="candidate",
            ready=True,
            claim_count=1,
            claims=[claim],
            evidence_obligations=[],
            citation_obligations=[],
        )
        mission = build_evidence_research_mission(report)

        self.assertEqual(mission.status, "no_research_needed")
        self.assertTrue(mission.ready)
        self.assertEqual(mission.tasks, [])
        self.assertEqual(mission.execution_status, "planned_only")

    def test_run_until_blocked_records_research_mission_and_routes_novelty_to_autoresearch_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material = root / "material"
            material.mkdir()
            (material / "main.tex").write_text(
                "We propose a new synthetic workflow for evidence-grounded writing. "
                "The method reduces review latency by 21 percent.\n",
                encoding="utf-8",
            )
            (material / "references.bib").write_text("@article{synthetic2026}\n", encoding="utf-8")
            (material / "notes.md").write_text("Synthetic experiment notes.\n", encoding="utf-8")
            state = run_until_blocked(root, material_path=material)

        self.assertEqual(state.facets.evidence, "durable_research_needed")
        self.assertEqual(state.next_actions[0].action_type, "start_autoresearch_goal")
        self.assertIn("evidence_research_mission", {ref["kind"] for ref in state.evidence_refs})
        rendered = json.dumps(state.to_public_dict(), ensure_ascii=False)
        self.assertNotIn("paper_full_tex", rendered)
        self.assertNotIn("omx autoresearch", rendered)


if __name__ == "__main__":
    unittest.main()
