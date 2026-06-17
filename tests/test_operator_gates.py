from __future__ import annotations

import unittest

from paperorchestra.feedback.operator_gates import _operator_actionable_failure


class OperatorGateTest(unittest.TestCase):
    def test_actionable_failure_compacts_blocked_candidate_progress(self) -> None:
        payload = _operator_actionable_failure(
            ["author"],
            "candidate blocked",
            category="candidate_gate",
            code="blocked_candidate",
            attempts=[
                {
                    "attempt_index": 1,
                    "gate_passed": False,
                    "gate_reasons": ["tier2_claim_safety_new_failures"],
                    "resolved_active_failures": ["old_issue"],
                    "new_tier2_failures": ["new_issue"],
                    "active_tier2_metric_delta": {
                        "improvements": [{"code": "old_issue", "before": 2, "after": 1, "delta": -1}],
                        "regressions": [],
                        "base_total": 2,
                        "candidate_total": 1,
                        "total_improved": True,
                    },
                }
            ],
        )

        self.assertEqual(payload["blocked_candidate_progress"]["kind"], "active_metric_improved_but_blocked")
        self.assertEqual(payload["blocked_candidate_progress"]["metric_improvements"][0]["code"], "old_issue")


if __name__ == "__main__":
    unittest.main()
