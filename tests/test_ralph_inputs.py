from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperorchestra.loop_engine.ralph.inputs import _split_path_ref, _validate_plan_quality_eval_identity


class RalphInputsTest(unittest.TestCase):
    def test_split_path_ref_extracts_path_and_sha(self) -> None:
        path, sha = _split_path_ref("/tmp/quality.json@sha256:abc123")

        self.assertEqual(path, Path("/tmp/quality.json").resolve())
        self.assertEqual(sha, "abc123")

    def test_validate_plan_quality_eval_identity_rejects_stale_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quality_path = Path(tmp) / "quality.json"
            quality_path.write_text("{}", encoding="utf-8")
            plan = {"reads": {"quality_eval": f"{quality_path}@sha256:wrong"}}

            with self.assertRaises(ValueError):
                _validate_plan_quality_eval_identity(plan, quality_path)


if __name__ == "__main__":
    unittest.main()
