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

    def test_external_residue_denylist_can_be_recorded_without_blocking_private_qa_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            denylist = root / "denylist.txt"
            denylist.write_text(
                "private-project-token\n"
                "regex:/Synthetic[A-Z]+Residue/\n",
                encoding="utf-8",
            )
            (root / "material.txt").write_text(
                "This private QA material mentions private-project-token and SyntheticAlphaResidue.\n",
                encoding="utf-8",
            )
            out = root / "scan.json"

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(root),
                    str(out),
                    "--allow-private-residue",
                    "--residue-denylist",
                    str(denylist),
                ],
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
            self.assertGreaterEqual(payload["allowed_private_residue_count"], 2)
            self.assertTrue(all(not item["blocking"] for item in payload["findings"]))

    def test_env_denylist_allows_private_residue_without_allowing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            denylist = root / "denylist.txt"
            denylist.write_text("private-project-token\n", encoding="utf-8")
            residue = root / "residue"
            residue.mkdir()
            (residue / "material.txt").write_text(
                "Private raw QA evidence mentions private-project-token.\n",
                encoding="utf-8",
            )
            residue_out = root / "residue-scan.json"
            env = {
                "PAPERO_RELEASE_SAFETY_ALLOW_PRIVATE_RESIDUE": "1",
                "PAPERO_RELEASE_SAFETY_RESIDUE_DENYLIST": str(denylist),
            }

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

    def test_external_residue_blocks_public_release_scan_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            denylist = root / "denylist.txt"
            denylist.write_text("private-project-token\n", encoding="utf-8")
            (root / "material.txt").write_text(
                "This public bundle mentions private-project-token.\n",
                encoding="utf-8",
            )
            out = root / "scan.json"

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), str(out), "--residue-denylist", str(denylist)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(proc.returncode, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertGreaterEqual(payload["blocking_finding_count"], 1)

    def test_domain_like_terms_do_not_trigger_without_external_denylist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "material.txt").write_text(
                "A public manuscript may mention domain-specific-public-term without a private profile.\n",
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

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["finding_count"], 0)

    def test_private_artifact_marker_still_blocks_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "material.txt").write_text("path contains paperorchestra-private-material\n", encoding="utf-8")
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
            self.assertEqual(payload["findings"][0]["code"], "private_artifact_path")

    def test_invalid_external_regex_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            denylist = root / "denylist.txt"
            denylist.write_text("regex:/[/\n", encoding="utf-8")
            (root / "material.txt").write_text("anything\n", encoding="utf-8")
            out = root / "scan.json"

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), str(out), "--residue-denylist", str(denylist)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("invalid residue denylist", proc.stderr)


if __name__ == "__main__":
    unittest.main()
