from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from paperorchestra.cli import main
from paperorchestra.orchestra_acceptance import (
    ACCEPTANCE_GATE_IDS,
    AcceptanceLedger,
    build_acceptance_ledger,
    render_acceptance_ledger_summary,
)


EXPECTED_GATE_IDS = (
    "state_contract_tests",
    "action_planner_scenario_tests",
    "fake_omx_unit_contract_tests",
    "real_bounded_omx_command_probes",
    "mcp_raw_and_attach_smoke",
    "mock_demo",
    "compile_export",
    "fresh_container_functional_smoke",
    "private_final_live_smoke_redacted",
    "private_leakage_scan",
    "no_unsupported_critical_claims",
    "no_unknown_refs_for_critical_claims",
    "citation_integrity",
    "supplied_figures_inventoried_matched_or_blocked",
    "hard_gates_no_fail_except_human_polish",
    "critic_consensus_near_ready_or_better",
    "verifier_evidence_completeness_no_leakage",
    "exported_pdf_tex_evidence_bundle",
    "readme_environment_skill_docs_updated",
)


@contextlib.contextmanager
def _chdir(path: str | Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _pass_entry(summary: str = "synthetic check passed") -> dict[str, object]:
    return {
        "status": "pass",
        "evidence_refs": [
            {
                "kind": "command",
                "summary": summary,
                "path": "evidence/synthetic-result.json",
                "sha256": "a" * 64,
            }
        ],
        "notes": ["synthetic public-safe note"],
    }


class OrchestraAcceptanceLedgerTests(unittest.TestCase):
    def test_gate_ids_match_runtime_contract_order(self) -> None:
        self.assertEqual(ACCEPTANCE_GATE_IDS, EXPECTED_GATE_IDS)

    def test_default_ledger_is_all_unknown_and_never_pass(self) -> None:
        ledger = build_acceptance_ledger()
        payload = ledger.to_dict()

        self.assertEqual(payload["schema_version"], "orchestrator-acceptance-ledger/1")
        self.assertEqual(payload["gate_count"], 19)
        self.assertEqual(payload["overall_status"], "unknown")
        self.assertEqual(payload["missing_gate_ids"], list(EXPECTED_GATE_IDS))
        self.assertTrue(all(gate["status"] == "unknown" for gate in payload["gates"]))
        self.assertNotEqual(payload["overall_status"], "pass")

    def test_all_pass_evidence_yields_pass(self) -> None:
        evidence = {gate_id: _pass_entry() for gate_id in EXPECTED_GATE_IDS}
        ledger = build_acceptance_ledger(evidence)

        self.assertEqual(ledger.overall_status, "pass")
        self.assertEqual(ledger.missing_gate_ids, [])
        self.assertTrue(all(gate.status == "pass" for gate in ledger.gates))

    def test_fail_precedence_over_blocked_and_unknown(self) -> None:
        ledger = build_acceptance_ledger(
            {
                "state_contract_tests": {"status": "blocked", "notes": ["tool unavailable"]},
                "mock_demo": {"status": "fail", "notes": ["synthetic failure"]},
            }
        )

        self.assertEqual(ledger.overall_status, "failed")

    def test_blocked_precedence_over_unknown_without_failures(self) -> None:
        ledger = build_acceptance_ledger(
            {"real_bounded_omx_command_probes": {"status": "blocked", "notes": ["omx unavailable"]}}
        )

        self.assertEqual(ledger.overall_status, "blocked")
        self.assertIn("state_contract_tests", ledger.missing_gate_ids)

    def test_missing_gate_ids_remain_unknown_even_with_some_passes(self) -> None:
        ledger = build_acceptance_ledger({"state_contract_tests": _pass_entry()})
        status_by_id = {gate.id: gate.status for gate in ledger.gates}

        self.assertEqual(ledger.overall_status, "unknown")
        self.assertEqual(status_by_id["state_contract_tests"], "pass")
        self.assertEqual(status_by_id["mock_demo"], "unknown")

    def test_rejects_unknown_gate_invalid_status_and_malformed_entries(self) -> None:
        invalid_inputs = [
            {"not_a_gate": _pass_entry()},
            {"state_contract_tests": {"status": "partial"}},
            {"state_contract_tests": {"status": "pass", "evidence_refs": "not-list"}},
            {"state_contract_tests": {"status": "pass", "evidence_refs": ["not-dict"]}},
            {"state_contract_tests": {"status": "pass", "notes": "not-list"}},
        ]
        for payload in invalid_inputs:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    build_acceptance_ledger(payload)

    def test_rejects_unsafe_supplied_evidence_instead_of_silent_redaction(self) -> None:
        unsafe_entries = [
            {"status": "pass", "evidence_refs": [{"kind": "command", "summary": "ok", "argv": ["omx", "status"]}]},
            {"status": "pass", "evidence_refs": [{"kind": "command", "summary": "PRIVATE marker"}]},
            {"status": "pass", "evidence_refs": [{"kind": "command", "summary": "run omx status now"}]},
            {"status": "pass", "evidence_refs": [{"kind": "artifact", "path": "/tmp/secret-result.json"}]},
            {"status": "pass", "evidence_refs": [{"kind": "artifact", "path": "../outside.json"}]},
            {"status": "pass", "notes": ["SECRET marker"]},
            {"status": "pass", "notes": [{"prompt": "raw prompt"}]},
        ]
        for entry in unsafe_entries:
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    build_acceptance_ledger({"state_contract_tests": entry})

    def test_accepts_intentional_redacted_placeholders(self) -> None:
        ledger = build_acceptance_ledger(
            {
                "private_final_live_smoke_redacted": {
                    "status": "blocked",
                    "evidence_refs": [
                        {"kind": "private_redacted", "summary": "<redacted>", "path": "<redacted>"}
                    ],
                    "notes": ["<redacted>"],
                }
            }
        )
        payload = ledger.to_dict()
        rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(ledger.overall_status, "blocked")
        self.assertIn("<redacted>", rendered)
        self.assertNotIn("PRIVATE", rendered)

    def test_summary_lists_counts_and_missing_without_leaking_private_strings(self) -> None:
        ledger = build_acceptance_ledger(
            {
                "state_contract_tests": _pass_entry(),
                "real_bounded_omx_command_probes": {"status": "blocked", "notes": ["tool unavailable"]},
            }
        )
        summary = render_acceptance_ledger_summary(ledger)

        self.assertIn("Acceptance ledger", summary)
        self.assertIn("overall: blocked", summary)
        self.assertIn("pass: 1", summary)
        self.assertIn("blocked: 1", summary)
        self.assertIn("unknown:", summary)
        self.assertIn("action_planner_scenario_tests", summary)
        self.assertNotIn("PRIVATE", summary)

    def test_json_round_trip_preserves_public_contract(self) -> None:
        original = build_acceptance_ledger({"state_contract_tests": _pass_entry()})
        restored = AcceptanceLedger.from_dict(json.loads(json.dumps(original.to_dict())))

        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_cli_json_defaults_to_all_unknown_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["acceptance-ledger", "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["overall_status"], "unknown")
        self.assertEqual(payload["gate_count"], 19)
        self.assertTrue(all(gate["status"] == "unknown" for gate in payload["gates"]))

    def test_cli_json_reflects_synthetic_evidence_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
            evidence_path = Path(tmp) / "evidence.json"
            evidence_path.write_text(
                json.dumps({"state_contract_tests": _pass_entry("state tests passed")}),
                encoding="utf-8",
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["acceptance-ledger", "--evidence", str(evidence_path), "--json"])
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        gate = next(item for item in payload["gates"] if item["id"] == "state_contract_tests")
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(payload["overall_status"], "unknown")

    def test_cli_rejects_unknown_malformed_or_private_evidence_file(self) -> None:
        invalid_payloads = [
            {"not_a_gate": _pass_entry()},
            {"state_contract_tests": {"status": "pass", "evidence_refs": "not-list"}},
            {"state_contract_tests": {"status": "pass", "evidence_refs": [{"summary": "PRIVATE marker"}]}},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp, _chdir(tmp):
                evidence_path = Path(tmp) / "bad-evidence.json"
                evidence_path.write_text(json.dumps(payload), encoding="utf-8")
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = main(["acceptance-ledger", "--evidence", str(evidence_path), "--json"])

                self.assertNotEqual(exit_code, 0)
                self.assertEqual(stdout.getvalue(), "")
                self.assertNotIn('"overall_status": "pass"', stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
