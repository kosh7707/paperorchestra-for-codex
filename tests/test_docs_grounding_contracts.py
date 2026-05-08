from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
QUALITY_DOC = REPO_ROOT / "docs" / "quality-gate-state-machine.md"
M0_DOC = REPO_ROOT / "docs" / "strict-review-quality-gate-hardening-m0.md"
CONTROLLED_SMOKE = REPO_ROOT / "scripts" / "controlled-quality-gate-smoke.py"

EXPECTED_GROUNDING_BLOCK = """Status: **normative development contract** for the claim-safe PaperOrchestra lifecycle.

Grounding contract: this document is grounded only in tracked repository artifacts.
Current grounding sources are `paperorchestra/`, `scripts/live-smoke-claim-safe.sh`, `scripts/pre-live-check.sh`, `scripts/controlled-quality-gate-smoke.py`, and `tests/`.
Ignored `review/` artifacts are historical audit outputs only and must not be cited here as current grounding.
"""

BANNED_REVIEW_ROOT = "review/fresh-full-live-smoke-operator-20260427T040938Z"
DEAD_REVIEW_SCRIPT = f"{BANNED_REVIEW_ROOT}/run-full-live-smoke.sh"


def _assert_tracked_path(path: Path) -> None:
    relative = path.resolve().relative_to(REPO_ROOT)
    if relative.parts and relative.parts[0] == "review":
        raise AssertionError(f"tracked doc-contract tests must not read ignored artifacts: {relative}")


def _read_tracked_text(path: Path) -> str:
    _assert_tracked_path(path)
    return path.read_text(encoding="utf-8")


class DocsGroundingContractTests(unittest.TestCase):
    def test_quality_gate_doc_uses_exact_tracked_grounding_contract(self) -> None:
        text = _read_tracked_text(QUALITY_DOC)

        self.assertIn(EXPECTED_GROUNDING_BLOCK, text)
        self.assertNotIn("Last grounded against code and live evidence", text)
        self.assertNotIn("Current grounding evidence", text)

    def test_banned_ignored_review_root_is_absent_from_tracked_docs(self) -> None:
        offenders = []
        for path in sorted((REPO_ROOT / "docs").glob("*.md")):
            if BANNED_REVIEW_ROOT in _read_tracked_text(path):
                offenders.append(str(path.relative_to(REPO_ROOT)))

        self.assertEqual([], offenders)

    def test_s2_code_surface_map_names_existing_modules(self) -> None:
        text = _read_tracked_text(QUALITY_DOC)

        self.assertNotIn("paperorchestra/semantic_scholar.py", text)
        self.assertIn("paperorchestra/s2_api.py", text)
        self.assertIn("paperorchestra/literature.py", text)
        self.assertTrue((REPO_ROOT / "paperorchestra" / "s2_api.py").exists())
        self.assertTrue((REPO_ROOT / "paperorchestra" / "literature.py").exists())

    def test_m0_doc_keeps_tracked_owner_lock_without_dead_review_script(self) -> None:
        m0_text = _read_tracked_text(M0_DOC)
        smoke_text = _read_tracked_text(CONTROLLED_SMOKE)

        self.assertNotIn(DEAD_REVIEW_SCRIPT, m0_text)
        self.assertIn("docs/strict-review-quality-gate-hardening-m0.md", smoke_text)

    def test_review_artifact_reads_are_rejected_by_test_helper(self) -> None:
        ignored_dir = "rev" + "iew"
        with self.assertRaisesRegex(AssertionError, "must not read ignored artifacts"):
            _assert_tracked_path(REPO_ROOT / ignored_dir / "local-only.md")


if __name__ == "__main__":
    unittest.main()
