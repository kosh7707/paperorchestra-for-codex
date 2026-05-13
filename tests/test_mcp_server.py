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


class _FakeTextStream:
    def __init__(self, data: bytes = b"") -> None:
        import io

        self.buffer = io.BytesIO(data)


def _content_length_message(payload: dict) -> bytes:
    import json

    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


def _newline_message(payload: dict) -> bytes:
    import json

    return json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"


class McpTransportFramingTests(unittest.TestCase):
    def _round_trip(self, payload: dict, *, transport: str) -> bytes:
        if transport == "newline":
            stdin = _FakeTextStream(_newline_message(payload))
        elif transport == "content-length":
            stdin = _FakeTextStream(_content_length_message(payload))
        else:  # pragma: no cover - test helper guard
            raise AssertionError(transport)
        stdout = _FakeTextStream()
        with patch("paperorchestra.mcp_server.sys.stdin", stdin), patch("paperorchestra.mcp_server.sys.stdout", stdout):
            message = mcp_server._read_message()
            self.assertIsInstance(message, dict)
            response = mcp_server._handle_request(message)
            self.assertIsInstance(response, dict)
            mcp_server._write_message(response)
        return stdout.buffer.getvalue()

    def test_newline_initialize_codex_2025_06_18_gets_newline_response(self) -> None:
        output = self._round_trip(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"elicitation": {}},
                    "clientInfo": {"name": "codex-mcp-client", "version": "0.129.0"},
                },
            },
            transport="newline",
        )
        self.assertTrue(output.endswith(b"\n"), output[:80])
        self.assertNotIn(b"Content-Length", output)
        import json

        payload = json.loads(output.decode("utf-8"))
        self.assertEqual(payload["result"]["serverInfo"]["name"], "paperorchestra-mcp")
        self.assertEqual(payload["result"]["protocolVersion"], "2025-06-18")

    def test_content_length_initialize_2024_11_05_keeps_content_length_response(self) -> None:
        output = self._round_trip(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "paperorchestra-mcp-smoke", "version": "0.1.0"},
                },
            },
            transport="content-length",
        )
        self.assertTrue(output.startswith(b"Content-Length: "), output[:80])
        header, body = output.split(b"\r\n\r\n", 1)
        self.assertIn(b"Content-Length", header)
        import json

        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["result"]["protocolVersion"], "2024-11-05")

    def test_newline_multi_message_flow_reaches_status_tool(self) -> None:
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"elicitation": {}},
                    "clientInfo": {"name": "codex-mcp-client", "version": "0.129.0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "status", "arguments": {"cwd": "."}}},
        ]
        stdin = _FakeTextStream(b"".join(_newline_message(message) for message in messages))
        stdout = _FakeTextStream()
        with patch("paperorchestra.mcp_server.sys.stdin", stdin), patch("paperorchestra.mcp_server.sys.stdout", stdout):
            while True:
                message = mcp_server._read_message()
                if message is None:
                    break
                response = mcp_server._handle_request(message)
                if response is not None:
                    mcp_server._write_message(response)
        import json

        responses = [json.loads(line) for line in stdout.buffer.getvalue().decode("utf-8").splitlines() if line.strip()]
        self.assertEqual([response.get("id") for response in responses], [1, 2, 3])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertTrue(any(tool["name"] == "status" for tool in responses[1]["result"]["tools"]))
        self.assertEqual(responses[2]["id"], 3)
        self.assertIn("result", responses[2])
