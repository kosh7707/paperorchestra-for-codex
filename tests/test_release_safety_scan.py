from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release-safety-scan.py"


class ReleaseSafetyScanTests(unittest.TestCase):
    def test_secret_findings_block_even_when_private_residue_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "evidence.txt").write_text(
                ("api" + "_key") + " = " + ("abcdefgh" + "ijklmnop") + "\n",
                encoding="utf-8",
            )
            out = root / "scan.json"

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), str(out), "--allow-private-residue"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(proc.returncode, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertEqual(payload["blocking_finding_count"], 1)
            self.assertEqual(payload["findings"][0]["family"], "secret")

    def test_private_residue_can_be_recorded_without_blocking_private_qa_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "material.txt").write_text(
                "This private QA material mentions " + ("c" + "ci") + " and " + ("AES" + "-GCM") + ".\n",
                encoding="utf-8",
            )
            out = root / "scan.json"

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), str(out), "--allow-private-residue"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertTrue(payload["allow_private_residue"])
            self.assertEqual(payload["blocking_finding_count"], 0)
            self.assertGreaterEqual(payload["allowed_private_residue_count"], 1)
            self.assertTrue(all(not item["blocking"] for item in payload["findings"]))

    def test_env_flag_allows_private_residue_without_allowing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            residue = root / "residue"
            residue.mkdir()
            (residue / "material.txt").write_text(
                "Private raw QA evidence mentions " + ("c" + "ci") + " and " + ("AES" + "-GCM") + ".\n",
                encoding="utf-8",
            )
            residue_out = root / "residue-scan.json"
            env = {"PAPERO_RELEASE_SAFETY_ALLOW_PRIVATE_RESIDUE": "1"}

            residue_proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(residue), str(residue_out)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**env},
                check=False,
            )

            self.assertEqual(residue_proc.returncode, 0, residue_proc.stderr + residue_proc.stdout)
            residue_payload = json.loads(residue_out.read_text(encoding="utf-8"))
            self.assertEqual(residue_payload["status"], "pass")
            self.assertTrue(residue_payload["allow_private_residue"])
            self.assertEqual(residue_payload["blocking_finding_count"], 0)
            self.assertGreater(residue_payload["allowed_private_residue_count"], 0)

            secret = root / "secret"
            secret.mkdir()
            (secret / "secret.txt").write_text(
                ("api" + "_key") + " = " + ("abcdefgh" + "ijklmnop") + "\n",
                encoding="utf-8",
            )
            secret_out = root / "secret-scan.json"

            secret_proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(secret), str(secret_out)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**env},
                check=False,
            )

            self.assertNotEqual(secret_proc.returncode, 0)
            secret_payload = json.loads(secret_out.read_text(encoding="utf-8"))
            self.assertEqual(secret_payload["status"], "fail")
            self.assertGreater(secret_payload["blocking_finding_count"], 0)
            self.assertTrue(all(item["family"] == "secret" for item in secret_payload["findings"]))

    def test_private_residue_blocks_public_release_scan_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "material.txt").write_text(
                "This public bundle mentions " + ("c" + "ci") + ".\n",
                encoding="utf-8",
            )
            out = root / "scan.json"

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), str(out)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(proc.returncode, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertGreaterEqual(payload["blocking_finding_count"], 1)


if __name__ == "__main__":
    unittest.main()
