from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class DomainNeutralityTests(unittest.TestCase):
    def test_public_tracked_regression_fixtures_do_not_preserve_private_crypto_corpus_terms(self) -> None:
        scoped_paths = [
            Path("tests/test_narrative_planning.py"),
            Path("tests/test_audit_surface_invariants.py"),
            Path("tests/test_strict_quality_gate_hardening.py"),
            Path("tests/test_jobs_and_pipeline.py"),
            Path("tests/test_pipeline_quality_and_operator_feedback.py"),
            Path("scripts/controlled-quality-gate-smoke.py"),
            Path("scripts/fresh-full-live-smoke-loop.sh"),
            Path("scripts/derive-fresh-smoke-inputs.py"),
            Path("scripts/release-safety-scan.py"),
        ]
        forbidden = [
            "protected-" + "channel",
            "Baseline-" + "128-X",
            "Baseline-" + "256-X",
            "Baseline-" + "X",
            "AES-" + "128-CCM",
            "Cha" + "Cha20-Poly1305",
            "secret per-direction masks",
            "sequence-number wraparound",
            "random-" + "oracle",
            "PRP/" + "PRF",
            "invariant-" + "safety",
            "Bench" + "Harness",
            "Bernstein" + "Lange",
            "fig_" + "encrypt",
            "adlen" + "=0",
            "Security Model and Proof",
            "proof_" + "preservation",
            "benchmark_" + "framing",
        ]

        offenders: list[str] = []
        for path in scoped_paths:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path}:{token}")

        self.assertEqual(offenders, [])

    def test_exact_private_corpus_names_remain_absent_from_tracked_files(self) -> None:
        patterns = [
            r"\bC" + r"CI\b",
            r"\bT" + r"DSC\b",
            "Secret-" + "Nonce",
            "material-packet-" + "tdsc",
            "AES-128-" + "CCI",
        ]
        proc = subprocess.run(
            ["git", "grep", "-n", "-I", "-E", "|".join(patterns), "--", "."],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
