from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.orchestra_claims import CitationObligation, ClaimCandidate, ClaimGraphReport, EvidenceObligation
from paperorchestra.orchestra_omx import build_planned_omx_invocation_evidence, build_research_mission_invocation_evidence
from paperorchestra.orchestra_research import build_evidence_research_mission
from paperorchestra.orchestrator import run_until_blocked


class OrchestraOmxInvocationTests(unittest.TestCase):
    def _claim(self, claim_type: str = "numeric") -> ClaimCandidate:
        return ClaimCandidate(
            claim_id="C1",
            claim_type=claim_type,
            graph_role="central_support",
            criticality="high",
            text_sha256="a" * 64,
            text_label="redacted-claim:aaaaaaaaaaaa",
            source_label="redacted-material:bbbbbbbbbbbb",
            source_sha256="b" * 64,
            raw_text="Synthetic raw claim should stay out of public OMX evidence.",
        )

    def _mission(self, claim_type: str = "numeric"):
        claim = self._claim(claim_type)
        report = ClaimGraphReport(
            schema_version="claim-graph/1",
            status="candidate",
            ready=True,
            claim_count=1,
            claims=[claim],
            evidence_obligations=[EvidenceObligation("E1", claim.claim_id, "research_needed", claim.criticality)],
            citation_obligations=[CitationObligation("R1", claim.claim_id, "unknown_reference", True)],
        )
        return build_evidence_research_mission(report)

    def test_planned_autoresearch_evidence_schema_and_hashes(self) -> None:
        evidence = build_planned_omx_invocation_evidence(
            surface="$autoresearch",
            purpose="evidence_research",
            input_payload={"task": "synthetic"},
            strict_required=True,
        )
        payload = evidence.to_public_dict()

        self.assertEqual(payload["schema_version"], "omx-invocation-evidence/1")
        self.assertEqual(payload["surface"], "$autoresearch")
        self.assertEqual(payload["execution_status"], "planned_only")
        self.assertEqual(payload["status"], "planned")
        self.assertIsNone(payload["return_code"])
        self.assertIsNone(payload["output_ref"])
        self.assertEqual(len(payload["command_or_skill_hash"]), 64)
        self.assertEqual(len(payload["input_bundle_hash"]), 64)

    def test_durable_autoresearch_goal_mission_builds_planned_invocation(self) -> None:
        mission = self._mission("novelty")
        evidence = build_research_mission_invocation_evidence(mission)

        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.surface, "$autoresearch-goal")
        self.assertEqual(evidence.execution_status, "planned_only")

    def test_deprecated_direct_legacy_autoresearch_command_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_planned_omx_invocation_evidence(
                surface="omx autoresearch",
                purpose="evidence_research",
                input_payload={"task": "synthetic"},
            )

    def test_public_evidence_hashes_input_without_raw_private_marker(self) -> None:
        marker = "SYNTHETIC_PRIVATE_OMX_INPUT_SHOULD_NOT_LEAK"
        evidence = build_planned_omx_invocation_evidence(
            surface="$autoresearch",
            purpose="evidence_research",
            input_payload={"private_raw_text": marker},
        )
        rendered = json.dumps(evidence.to_public_dict(), ensure_ascii=False)

        self.assertNotIn(marker, rendered)
        self.assertIn("input_bundle_hash", rendered)
        self.assertFalse(evidence.private_material_included)

    def test_run_until_blocked_records_planned_omx_invocation_for_novelty_mission(self) -> None:
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

        invocations = [ref["payload"] for ref in state.evidence_refs if ref["kind"] == "omx_invocation_evidence"]
        self.assertTrue(invocations)
        self.assertEqual(invocations[0]["surface"], "$autoresearch-goal")
        self.assertEqual(invocations[0]["execution_status"], "planned_only")
        self.assertIsNone(invocations[0]["return_code"])

    def test_planned_only_evidence_never_reports_pass_or_success_return_code(self) -> None:
        evidence = build_research_mission_invocation_evidence(self._mission("numeric"))
        assert evidence is not None
        payload = evidence.to_public_dict()

        self.assertNotEqual(payload["status"], "pass")
        self.assertIsNone(payload["return_code"])
        self.assertIsNone(payload["output_ref"])
        self.assertEqual(payload["execution_status"], "planned_only")

    def test_direct_invalid_planned_evidence_construction_is_rejected(self) -> None:
        from paperorchestra.orchestra_omx import OmxInvocationEvidence

        kwargs = {
            "schema_version": "omx-invocation-evidence/1",
            "surface": "$autoresearch",
            "purpose": "evidence_research",
            "strict_required": True,
            "command_or_skill_hash": "a" * 64,
            "input_bundle_hash": "b" * 64,
        }
        invalid_overrides = [
            {"status": "pass"},
            {"execution_status": "executed"},
            {"return_code": 0},
            {"output_ref": "out.json"},
            {"private_material_included": True},
            {"private_safe_summary": False},
            {"schema_version": "omx-invocation-evidence/0"},
            {"surface": "omx autoresearch"},
        ]
        for override in invalid_overrides:
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    OmxInvocationEvidence(**{**kwargs, **override})


if __name__ == "__main__":
    unittest.main()
