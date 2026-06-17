from __future__ import annotations

import unittest

from paperorchestra.feedback.operator_incorporation import _issue_incorporation_detailed


class OperatorIncorporationTest(unittest.TestCase):
    def test_issue_incorporation_reflects_target_section_change(self) -> None:
        before = r"\section{Method} Old method text."
        after = r"\section{Method} New method text adds sanitizer evidence."
        issues = [
            {
                "id": "issue-1",
                "target_section": "Method",
                "rationale": "Missing sanitizer evidence.",
                "suggested_action": "Add sanitizer evidence.",
            }
        ]

        result = _issue_incorporation_detailed(issues, before, after, blocking_codes=[])

        self.assertEqual(result[0]["status"], "reflected")
        self.assertTrue(result[0]["changed"])
        self.assertIn("sanitizer", result[0]["matched_terms"])

    def test_issue_incorporation_defers_when_claim_safety_blocks(self) -> None:
        before = r"\section{Results} Old result."
        after = r"\section{Results} New unsupported result."
        issues = [{"id": "issue-1", "target_section": "Results", "rationale": "Update result."}]

        result = _issue_incorporation_detailed(
            issues,
            before,
            after,
            blocking_codes=["unsupported_comparative_claim"],
        )

        self.assertEqual(result[0]["status"], "blocked_by_claim_safety")


if __name__ == "__main__":
    unittest.main()
