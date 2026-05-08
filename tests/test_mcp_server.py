from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperorchestra import mcp_server


class McpProviderSplitTests(unittest.TestCase):
    def test_apply_operator_feedback_schema_and_handler_pass_citation_provider(self) -> None:
        tools = {tool["name"]: tool for tool in mcp_server.TOOLS}
        props = tools["apply_operator_feedback"]["inputSchema"]["properties"]
        self.assertIn("citation_provider", props)
        self.assertIn("citation_provider_command", props)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("paperorchestra.mcp_server.apply_operator_feedback", return_value=(root/"execution.json", {"verdict": "human_needed"})) as apply:
                result = mcp_server.tool_apply_operator_feedback({
                    "cwd": str(root),
                    "imported_feedback_path": str(root/"imported.json"),
                    "provider": "mock",
                    "citation_provider": "shell",
                    "citation_provider_command": '["bash","provider-wrap.sh","web"]',
                })
        self.assertFalse(result["isError"])
        self.assertEqual(apply.call_args.kwargs["citation_provider_name"], "shell")
        self.assertEqual(apply.call_args.kwargs["citation_provider_command"], '["bash","provider-wrap.sh","web"]')
