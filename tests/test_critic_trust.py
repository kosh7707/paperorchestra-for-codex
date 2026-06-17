from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import main as cli_main
from paperorchestra.critic_trust import build_critic_trust_card


def _write_wrapper(root: Path) -> str:
    wrapper = root / "provider-wrap.sh"
    wrapper.write_text("#!/usr/bin/env bash\ncodex --search exec\n", encoding="utf-8")
    wrapper.chmod(0o755)
    contract = {
        "schema_version": "provider-wrapper-contract/1",
        "wrapper_path": str(wrapper.resolve()),
        "wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
        "modes": {
            "web": {
                "trace_wrapped": True,
                "web_search_capable": True,
                "exec_argv_prefix": ["codex", "--search", "exec"],
            }
        },
    }
    (root / "provider-wrap.contract.json").write_text(json.dumps(contract), encoding="utf-8")
    return json.dumps(["bash", str(wrapper), "web"])


class CriticTrustTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_allowlist = os.environ.get("PAPERO_ALLOWED_PROVIDER_BINARIES")
        os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = "codex,bash"

    def tearDown(self) -> None:
        if self.old_allowlist is None:
            os.environ.pop("PAPERO_ALLOWED_PROVIDER_BINARIES", None)
        else:
            os.environ["PAPERO_ALLOWED_PROVIDER_BINARIES"] = self.old_allowlist

    def test_mock_heuristic_is_not_live_critic(self) -> None:
        card = build_critic_trust_card(provider_name="mock", citation_evidence_mode="heuristic")

        self.assertEqual(card["trust_tier"], "mock_smoke")
        self.assertFalse(card["live_critic_claim_allowed"])
        self.assertIn("provider=mock", card["blockers"])

    def test_shell_heuristic_is_partial_not_full_live_critic(self) -> None:
        card = build_critic_trust_card(
            provider_name="shell",
            provider_command='["codex","exec"]',
            citation_evidence_mode="heuristic",
        )

        self.assertEqual(card["trust_tier"], "live_model_review")
        self.assertEqual(card["citation_trust_tier"], "heuristic_citation")
        self.assertFalse(card["live_critic_claim_allowed"])
        self.assertIn("citation_evidence_mode=heuristic", card["blockers"])

    def test_shell_web_search_is_live_critic(self) -> None:
        card = build_critic_trust_card(
            provider_name="shell",
            provider_command='["codex","--search","exec"]',
            citation_evidence_mode="web",
        )

        self.assertEqual(card["trust_tier"], "web_citation_review")
        self.assertEqual(card["citation_trust_tier"], "web_citation_review")
        self.assertTrue(card["live_critic_claim_allowed"])
        self.assertEqual(card["blockers"], [])

    def test_wrapper_backed_web_provider_is_live_critic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = _write_wrapper(Path(tmp))
            card = build_critic_trust_card(
                provider_name="shell",
                provider_command=command,
                citation_evidence_mode="web",
            )

        self.assertEqual(card["trust_tier"], "web_citation_review")
        self.assertTrue(card["web_search_configured"])
        self.assertTrue(card["live_critic_claim_allowed"])
        self.assertEqual(card["blockers"], [])

    def test_critic_preflight_cli_outputs_trust_card(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["critic-preflight", "--provider", "mock", "--citation-evidence-mode", "heuristic"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["critic_trust"]["trust_tier"], "mock_smoke")
        self.assertFalse(payload["critic_trust"]["live_critic_claim_allowed"])

    def test_critique_live_refuses_non_live_trust_tier_before_running_reviews(self) -> None:
        with patch("paperorchestra.cli.review_current_paper") as review:
            code = cli_main(["critique", "--provider", "mock", "--citation-evidence-mode", "heuristic", "--live"])

        self.assertEqual(code, 1)
        review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
