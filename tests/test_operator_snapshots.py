from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paperorchestra.feedback.operator_snapshots import _restore_tree, _snapshot_tree


class OperatorSnapshotsTest(unittest.TestCase):
    def test_snapshot_tree_restores_files_and_removes_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "refs"
            nested = root / "nested"
            nested.mkdir(parents=True)
            original = nested / "paper.pdf"
            original.write_text("before", encoding="utf-8")

            snapshot = _snapshot_tree(root)
            original.write_text("after", encoding="utf-8")
            (root / "new.txt").write_text("new", encoding="utf-8")

            _restore_tree(snapshot)

            self.assertEqual(original.read_text(encoding="utf-8"), "before")
            self.assertFalse((root / "new.txt").exists())


if __name__ == "__main__":
    unittest.main()
