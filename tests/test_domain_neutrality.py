from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


PUBLIC_PRIVATE_CORPUS_SCAN_PATHS = [
    Path("tests/test_citation_alias_canonicalization.py"),
    Path("tests/test_citation_and_session.py"),
    Path("tests/test_citation_integrity.py"),
    Path("tests/test_citation_path_smoke.py"),
    Path("tests/test_citation_support_provenance.py"),
    Path("tests/test_citation_support_review_v3.py"),
    Path("tests/test_narrative_planning.py"),
    Path("tests/test_audit_surface_invariants.py"),
    Path("tests/test_strict_quality_gate_hardening.py"),
    Path("tests/test_jobs_and_pipeline.py"),
    Path("tests/test_orchestra_citation_quality.py"),
    Path("tests/test_orchestra_references.py"),
    Path("tests/test_pipeline_quality_and_operator_feedback.py"),
    Path("tests/test_rendered_reference_duplicate_identity.py"),
    Path("scripts/controlled-quality-gate-smoke.py"),
    Path("scripts/fresh-full-live-smoke-loop.sh"),
    Path("scripts/derive-fresh-smoke-inputs.py"),
    Path("scripts/release-safety-scan.py"),
]


class DomainNeutralityTests(unittest.TestCase):
    def test_citation_regression_fixtures_are_in_private_corpus_scan_scope(self) -> None:
        required_paths = {
            Path("tests/test_citation_alias_canonicalization.py"),
            Path("tests/test_citation_and_session.py"),
            Path("tests/test_citation_integrity.py"),
            Path("tests/test_citation_path_smoke.py"),
            Path("tests/test_citation_support_provenance.py"),
            Path("tests/test_citation_support_review_v3.py"),
            Path("tests/test_orchestra_citation_quality.py"),
            Path("tests/test_orchestra_references.py"),
            Path("tests/test_rendered_reference_duplicate_identity.py"),
        }

        self.assertEqual(required_paths - set(PUBLIC_PRIVATE_CORPUS_SCAN_PATHS), set())

    def test_public_tracked_regression_fixtures_do_not_preserve_private_crypto_corpus_terms(self) -> None:
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
        for path in PUBLIC_PRIVATE_CORPUS_SCAN_PATHS:
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
            [
                "git",
                "grep",
                "-n",
                "-I",
                "-E",
                "|".join(patterns),
                "--",
                ".",
                f":!{Path(__file__).resolve().relative_to(Path.cwd()).as_posix()}",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
