from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.loop_engine.ralph.semantic_recheck import (
    _semantic_recheck_gate_summary,
    _validation_failing_codes_from_repair,
)


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


if __name__ == "__main__":
    unittest.main()
