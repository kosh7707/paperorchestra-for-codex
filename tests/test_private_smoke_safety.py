from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEAK_SCRIPT = ROOT / "scripts" / "check-private-leakage.py"
PREP_SCRIPT = ROOT / "scripts" / "prepare-private-smoke-materials.py"


class PrivateSmokeSafetyTests(unittest.TestCase):
    def _run_json(self, argv: list[str]) -> tuple[int, dict]:
        proc = subprocess.run(argv, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            payload = json.loads(proc.stdout)
        except Exception as exc:  # pragma: no cover - assertion helper
            raise AssertionError(f"stdout was not JSON: {proc.stdout!r}\nstderr={proc.stderr!r}") from exc
        return proc.returncode, payload

    def test_leakage_scanner_ok_when_deny_token_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "public.md"
            target.write_text("safe synthetic text\n", encoding="utf-8")
            deny = root / "denylist.txt"
            deny.write_text("SYNTHETIC_PRIVATE_TOKEN\n", encoding="utf-8")
            code, payload = self._run_json([sys.executable, str(LEAK_SCRIPT), "--denylist", str(deny), "--paths", str(target), "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["match_count"], 0)
        self.assertEqual(payload["scan_mode"], "explicit_paths")

    def test_leakage_scanner_blocks_and_redacts_token_and_path(self) -> None:
        private_token = "SYNTHETIC_PRIVATE_TOKEN"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / f"{private_token}_notes.md"
            target.write_text(f"contains {private_token}\n", encoding="utf-8")
            deny = root / "denylist.txt"
            deny.write_text(private_token + "\n", encoding="utf-8")
            code, payload = self._run_json([sys.executable, str(LEAK_SCRIPT), "--denylist", str(deny), "--paths", str(target), "--json"])
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["match_count"], 1)
        self.assertNotIn(private_token, rendered)
        self.assertNotIn(str(target), rendered)
        self.assertEqual(len(payload["matches"][0]["token_sha256"]), 64)
        self.assertEqual(len(payload["matches"][0]["path_sha256"]), 64)

    def test_leakage_scanner_defaults_to_tracked_file_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            deny = Path(tmp) / "denylist.txt"
            absent_token = "TOKEN_THAT_SHOULD_NOT_EXIST" + "_IN_REPO_12345"
            deny.write_text(absent_token + "\n", encoding="utf-8")
            code, payload = self._run_json([sys.executable, str(LEAK_SCRIPT), "--denylist", str(deny), "--root", str(ROOT), "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["scan_mode"], "tracked_files")

    def test_material_prep_refuses_output_inside_repo_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_zip = Path(tmp) / "synthetic-private.zip"
            with zipfile.ZipFile(source_zip, "w") as zf:
                zf.writestr("material/idea.md", "synthetic private content\n")
            inside_repo = ROOT / ".tmp-private-prep-output"
            if inside_repo.exists():
                import shutil

                shutil.rmtree(inside_repo)
            code, payload = self._run_json(
                [sys.executable, str(PREP_SCRIPT), "--source-zip", str(source_zip), "--output-dir", str(inside_repo), "--json"]
            )

        self.assertNotEqual(code, 0)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocker"], "output_inside_repo")
        self.assertFalse(inside_repo.exists())

    def test_material_prep_extracts_synthetic_zip_outside_repo_with_redacted_manifest(self) -> None:
        raw_private = "PRIVATE_ZIP_CONTENT_SHOULD_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            source_zip = Path(tmp) / "synthetic-private.zip"
            with zipfile.ZipFile(source_zip, "w") as zf:
                zf.writestr("material/idea.md", raw_private)
                zf.writestr("figures/supplied_architecture_diagram.pdf", b"figure-bytes")
            output_dir = Path(tmp) / "out"
            code, payload = self._run_json(
                [sys.executable, str(PREP_SCRIPT), "--source-zip", str(source_zip), "--output-dir", str(output_dir), "--json"]
            )
            rendered = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["manifest"]["private_safe_summary"])
        self.assertEqual(payload["manifest"]["file_count"], 2)
        self.assertEqual(payload["manifest"]["extensions"][".md"], 1)
        self.assertEqual(payload["manifest"]["extensions"][".pdf"], 1)
        self.assertNotIn(raw_private, rendered)
        self.assertTrue(payload["manifest"]["files"][0]["sha256"])


if __name__ == "__main__":
    unittest.main()
