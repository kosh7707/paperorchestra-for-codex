from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.loop_engine.ralph.action_dispatch_citation_repair import citation_repair_failure_payload
from paperorchestra.loop_engine.ralph.semantic_gate_summary import _semantic_recheck_gate_summary
from paperorchestra.loop_engine.ralph.semantic_validation import _validation_failing_codes_from_repair


class RalphSemanticRecheckTest(unittest.TestCase):
    def test_semantic_recheck_reports_targeted_non_improvement_blocker(self) -> None:
        summary, blockers = _semantic_recheck_gate_summary(
            {
                "status": "fail",
                "citation_integrity": {
                    "targeted": True,
                    "improved": False,
                    "before": {"target_issue_count": 2},
                    "after": {"target_issue_count": 2},
                },
            }
        )

        self.assertEqual(blockers, ["citation_integrity_not_improved"])
        self.assertEqual(summary["citation_integrity"]["before_count"], 2)
        self.assertEqual(summary["citation_integrity"]["after_count"], 2)

    def test_validation_failing_codes_from_repair_reads_validation_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            validation_path = Path(tmp) / "validation.json"
            validation_path.write_text(
                json.dumps({"issues": [{"code": "unknown_citation"}, {"code": "numeric_grounding"}]}),
                encoding="utf-8",
            )

            codes = _validation_failing_codes_from_repair({"validation": {"path": str(validation_path)}})

        self.assertEqual(codes, ["numeric_grounding", "unknown_citation"])

    def test_citation_repair_failure_payload_projects_semantic_recheck_failure(self) -> None:
        repair = {
            "reason": "semantic_recheck_failed",
            "issue_count": 4,
            "validation": {"ok": False, "blocking_issue_count": 2},
            "semantic_recheck": {
                "status": "fail",
                "high_risk_claim_sweep": {
                    "targeted": True,
                    "improved": False,
                    "before": {"item_count": 3},
                    "after": {"item_count": 3},
                    "path": "sweep.json",
                    "sha256": "sha256:sweep",
                },
            },
        }

        payload = citation_repair_failure_payload("citation_repair_failed", repair)

        self.assertEqual(payload["reason"], "semantic_recheck_failed")
        self.assertEqual(payload["validation"]["failing_codes"], ["validation_failed"])
        self.assertEqual(payload["semantic_recheck_blockers"], ["high_risk_claim_sweep_not_improved"])
        self.assertEqual(payload["semantic_recheck"]["high_risk_claim_sweep"]["after_count"], 3)
        self.assertIn("Inspect semantic_recheck blockers", payload["next_steps"][0])


if __name__ == "__main__":
    unittest.main()
