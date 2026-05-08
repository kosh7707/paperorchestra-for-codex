from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra.cli import main as cli_main


class OperatorFeedbackProviderSplitTests(unittest.TestCase):
    def test_apply_operator_feedback_cli_passes_explicit_citation_provider(self) -> None:
        stdout = io.StringIO()
        with patch("paperorchestra.cli.apply_operator_feedback", return_value=(Path("execution.json"), {"verdict": "human_needed"})) as apply:
            with contextlib.redirect_stdout(stdout):
                code = cli_main([
                    "apply-operator-feedback",
                    "--imported-feedback", "imported.json",
                    "--provider", "shell",
                    "--provider-command", '["codex","exec"]',
                    "--citation-provider", "shell",
                    "--citation-provider-command", '["bash","provider-wrap.sh","web"]',
                ])
        self.assertEqual(code, 0)
        self.assertEqual(apply.call_args.kwargs["citation_provider_name"], "shell")
        self.assertEqual(apply.call_args.kwargs["citation_provider_command"], '["bash","provider-wrap.sh","web"]')
        self.assertEqual(json.loads(stdout.getvalue())["execution"]["verdict"], "human_needed")
