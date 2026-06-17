from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paperorchestra.loop_engine.ralph.artifacts import _write_execution_artifact


class RalphExecutionArtifactTest(unittest.TestCase):
    def test_write_execution_artifact_finalizes_pending_approval_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "execution.json"
            payload = {
                "_reserved_execution_path": str(path),
                "candidate_approval": {"source_execution_sha256": "pending_until_execution_write"},
                "value": "kept",
            }

            written = _write_execution_artifact(None, payload)
            stored = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(written, path)
        self.assertTrue(stored["candidate_approval"]["source_execution_sha256"].startswith("sha256:"))
        self.assertEqual(stored["value"], "kept")
        self.assertNotIn("_reserved_execution_path", stored)


if __name__ == "__main__":
    unittest.main()
