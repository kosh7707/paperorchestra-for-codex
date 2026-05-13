from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import main as cli_main
from paperorchestra.mcp_server import TOOL_HANDLERS, TOOLS
from paperorchestra.models import InputBundle
from paperorchestra.orchestra_acceptance import build_acceptance_ledger
from paperorchestra.orchestra_consensus import ConsensusPolicy, CriticVerdict
from paperorchestra.orchestra_scoring import SCORE_DIMENSIONS, ScholarlyScore, ScoreDimensionAssessment, ScoringBundleBuilder
from paperorchestra.orchestra_state import HardGateStatus, OrchestraFacets, OrchestraState
from paperorchestra.orchestra_verifier import (
    VERIFIER_CHECKLIST_SCHEMA_VERSION,
    build_verifier_evidence_checklist,
    verifier_acceptance_evidence,
    verifier_evidence_checklist_path,
    write_verifier_evidence_checklist,
)
from paperorchestra.session import create_session


def _complete_dimensions(score: float = 90.0) -> dict[str, ScoreDimensionAssessment]:
    return {
        dimension: ScoreDimensionAssessment(
            score=score,
            confidence="medium",
            rationale=f"{dimension} rationale",
            evidence_links=[f"artifacts/{dimension}.json"],
        )
        for dimension in SCORE_DIMENSIONS
    }


def _bundle() -> object:
    return ScoringBundleBuilder().build(
        phase="final",
        manuscript_sha256="a" * 64,
        required_artifacts={"paper": "artifacts/paper.full.tex", "citations": "artifacts/citation-quality.json"},
        compressed_evidence={"summary": "safe compressed evidence"},
    )


def _bundle_with(*, manuscript_sha256: str = "a" * 64, required_artifacts: dict[str, str] | None = None) -> object:
    return ScoringBundleBuilder().build(
        phase="final",
        manuscript_sha256=manuscript_sha256,
        required_artifacts={} if required_artifacts is None else required_artifacts,
        compressed_evidence={"summary": "safe compressed evidence"},
    )


def _score(overall: float = 90.0, readiness_band: str = "near_ready") -> ScholarlyScore:
    return ScholarlyScore(
        overall=overall,
        readiness_band=readiness_band,
        evidence_links=["artifacts/score-input.json"],
        dimensions=_complete_dimensions(overall),
    )


def _consensus(verdict: str = "near_ready"):
    return ConsensusPolicy().evaluate(
        [
            CriticVerdict("critic-a", verdict, ["artifacts/score.json"]),
            CriticVerdict("critic-b", verdict, ["artifacts/score.json"]),
        ]
    )


def _state(hard_gate_status: str = "pass") -> OrchestraState:
    return OrchestraState.new(
        cwd="/tmp/synthetic",
        facets=OrchestraFacets(session="draft_available", quality="human_finalization_candidate"),
        hard_gates=HardGateStatus(status=hard_gate_status, failures=["unsupported_critical_claim"] if hard_gate_status == "fail" else []),
    )


def _tool_names() -> set[str]:
    return {tool["name"] for tool in TOOLS}


def _decode_text_result(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


class OrchestraVerifierTests(unittest.TestCase):
    def test_complete_score_consensus_and_gates_produce_pass_checklist(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle(),
            _score(),
            _consensus(),
            compiled=True,
            exported=True,
            artifact_refs={"checklist": "artifacts/verifier_evidence_checklist.json"},
        )
        payload = checklist.to_public_dict()

        self.assertEqual(payload["schema_version"], VERIFIER_CHECKLIST_SCHEMA_VERSION)
        self.assertEqual(payload["overall_status"], "pass")
        self.assertTrue(payload["private_safe_summary"])
        self.assertTrue(all(item["status"] == "pass" for item in payload["items"]))

    def test_acceptance_evidence_maps_directly_to_ledger_gate(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle(),
            _score(),
            _consensus(),
            compiled=True,
            exported=True,
            artifact_refs={"checklist": "artifacts/verifier_evidence_checklist.json"},
        )
        evidence = verifier_acceptance_evidence(checklist)
        ledger = build_acceptance_ledger(evidence)
        gate = next(gate for gate in ledger.gates if gate.id == "verifier_evidence_completeness_no_leakage")

        self.assertEqual(gate.status, "pass")
        self.assertEqual(gate.evidence_refs[0]["kind"], "verifier/checklist")

    def test_missing_scoring_bundle_blocks_even_with_high_score(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            None,
            _score(99.0),
            _consensus(),
            compiled=True,
            exported=True,
        )

        self.assertEqual(checklist.overall_status, "blocked")
        self.assertEqual(checklist.item_status("scoring_bundle_complete"), "blocked")

    def test_non_hex_manuscript_hash_fails_scoring_bundle_item(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle_with(manuscript_sha256="g" * 64, required_artifacts={"paper": "artifacts/paper.full.tex"}),
            _score(),
            _consensus(),
            compiled=True,
            exported=True,
        )

        self.assertEqual(checklist.overall_status, "fail")
        self.assertEqual(checklist.item_status("scoring_bundle_complete"), "fail")

    def test_empty_required_artifact_refs_block_scoring_bundle_item(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle_with(required_artifacts={}),
            _score(),
            _consensus(),
            compiled=True,
            exported=True,
        )

        self.assertEqual(checklist.overall_status, "blocked")
        self.assertEqual(checklist.item_status("scoring_bundle_complete"), "blocked")

    def test_unsafe_required_artifact_ref_fails_without_reproducing_value(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle_with(required_artifacts={"paper": "/tmp/PRIVATE_PAPER_PATH.tex"}),
            _score(),
            _consensus(),
            compiled=True,
            exported=True,
        )
        rendered = json.dumps(checklist.to_public_dict(), ensure_ascii=False)

        self.assertEqual(checklist.overall_status, "fail")
        self.assertEqual(checklist.item_status("scoring_bundle_complete"), "fail")
        self.assertNotIn("/tmp/PRIVATE_PAPER_PATH.tex", rendered)

    def test_invalid_score_blocks_verifier(self) -> None:
        dimensions = _complete_dimensions()
        dimensions.pop("source_grounding")
        invalid_score = ScholarlyScore(overall=90.0, readiness_band="near_ready", evidence_links=["score.json"], dimensions=dimensions)
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle(),
            invalid_score,
            _consensus(),
            compiled=True,
            exported=True,
        )

        self.assertEqual(checklist.overall_status, "blocked")
        self.assertEqual(checklist.item_status("score_valid_and_evidence_linked"), "blocked")

    def test_one_critic_blocks_two_or_more_consensus_item(self) -> None:
        one_critic = ConsensusPolicy().evaluate([CriticVerdict("critic-a", "near_ready", ["score.json"])])
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle(),
            _score(),
            one_critic,
            compiled=True,
            exported=True,
        )

        self.assertEqual(checklist.overall_status, "blocked")
        self.assertEqual(checklist.item_status("critic_consensus_two_or_more"), "blocked")

    def test_disagreeing_critics_block_near_ready_consensus_and_do_not_claim_live_critic(self) -> None:
        disagreement = ConsensusPolicy().evaluate(
            [
                CriticVerdict("critic-a", "near_ready", ["score.json"]),
                CriticVerdict("critic-b", "not_ready", ["score.json"]),
            ]
        )
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle(),
            _score(),
            disagreement,
            compiled=True,
            exported=True,
        )
        rendered = json.dumps(checklist.to_public_dict(), ensure_ascii=False)

        self.assertEqual(checklist.overall_status, "blocked")
        self.assertEqual(checklist.item_status("critic_consensus_near_ready_or_better"), "blocked")
        self.assertNotIn("live Critic approved", rendered)
        self.assertNotIn("omx ", rendered)

    def test_hard_gate_failure_fails_despite_high_score_and_consensus(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state("fail"),
            _bundle(),
            _score(99.0),
            _consensus("near_ready"),
            compiled=True,
            exported=True,
        )

        self.assertEqual(checklist.overall_status, "fail")
        self.assertEqual(checklist.item_status("hard_gates_no_fail"), "fail")

    def test_compile_export_missing_is_blocked_not_pass(self) -> None:
        checklist = build_verifier_evidence_checklist(
            _state(),
            _bundle(),
            _score(),
            _consensus(),
            compiled=True,
            exported=False,
        )

        self.assertEqual(checklist.overall_status, "blocked")
        self.assertEqual(checklist.item_status("compile_export_accounted_for"), "blocked")

    def test_unsafe_artifact_refs_fail_closed_without_reproducing_unsafe_values(self) -> None:
        unsafe_cases = [
            {"bad": "omx ralph --prompt something"},
            {"bad": "/tmp/private/path.json"},
            {"bad": "PRIVATE_SECRET_VALUE"},
            {"bad": {"prompt": "do the private thing"}},
            {"bad": {"raw_text": "raw manuscript excerpt"}},
        ]
        for refs in unsafe_cases:
            with self.subTest(refs=refs):
                checklist = build_verifier_evidence_checklist(
                    _state(),
                    _bundle(),
                    _score(),
                    _consensus(),
                    compiled=True,
                    exported=True,
                    artifact_refs=refs,
                )
                rendered = json.dumps(checklist.to_public_dict(), ensure_ascii=False)
                self.assertEqual(checklist.overall_status, "fail")
                self.assertEqual(checklist.item_status("public_safety_no_raw_private_evidence"), "fail")
                self.assertNotIn("PRIVATE_SECRET_VALUE", rendered)
                self.assertNotIn("/tmp/private/path.json", rendered)
                self.assertNotIn("omx ralph", rendered)
                self.assertNotIn("raw manuscript excerpt", rendered)

    def test_write_verifier_evidence_checklist_uses_session_artifact_path_without_leaking_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["idea.md", "experimental_log.md", "template.tex", "guidelines.md"]:
                (root / name).write_text("synthetic\n", encoding="utf-8")
            figures = root / "figures"
            figures.mkdir()
            create_session(
                root,
                InputBundle(
                    str(root / "idea.md"),
                    str(root / "experimental_log.md"),
                    str(root / "template.tex"),
                    str(root / "guidelines.md"),
                    str(figures),
                ),
                allow_outside_workspace=True,
            )
            path, payload = write_verifier_evidence_checklist(root)
            expected = verifier_evidence_checklist_path(root)
            rendered = json.dumps(payload, ensure_ascii=False)
            exists = path.exists()

        self.assertEqual(path, expected)
        self.assertTrue(exists)
        self.assertNotIn(str(root), rendered)
        self.assertEqual(payload["schema_version"], VERIFIER_CHECKLIST_SCHEMA_VERSION)
        self.assertEqual(payload["overall_status"], "blocked")

    def test_cli_verify_evidence_checklist_json_and_explicit_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "PRIVATE_OUTPUT_SHOULD_NOT_LEAK.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = cli_main(["verify-evidence-checklist", "--output", str(output), "--json"])
            payload = json.loads(stdout.getvalue())
            output_exists = output.exists()
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(exit_code, 0)
        self.assertTrue(output_exists)
        self.assertEqual(payload["schema_version"], VERIFIER_CHECKLIST_SCHEMA_VERSION)
        self.assertEqual(payload["overall_status"], "blocked")
        self.assertNotIn(str(output), rendered)
        self.assertNotIn("PRIVATE_OUTPUT_SHOULD_NOT_LEAK", rendered)

    def test_mcp_verify_evidence_checklist_tool_is_registered_and_public_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "PRIVATE_MCP_OUTPUT_SHOULD_NOT_LEAK.json"
            payload = _decode_text_result(TOOL_HANDLERS["verify_evidence_checklist"]({"cwd": tmp, "output": str(output)}))
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertIn("verify_evidence_checklist", _tool_names())
        self.assertEqual(payload["schema_version"], VERIFIER_CHECKLIST_SCHEMA_VERSION)
        self.assertEqual(payload["overall_status"], "blocked")
        self.assertNotIn(str(output), rendered)
        self.assertNotIn("PRIVATE_MCP_OUTPUT_SHOULD_NOT_LEAK", rendered)
