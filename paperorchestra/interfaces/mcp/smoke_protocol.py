from __future__ import annotations

import json
import os
import select
import time
from typing import Any, BinaryIO

TRANSPORT_CONTENT_LENGTH = "content-length"
TRANSPORT_NEWLINE = "newline"
TRANSPORT_CHOICES = (TRANSPORT_CONTENT_LENGTH, TRANSPORT_NEWLINE)


def _readline(stream: BinaryIO, timeout_sec: float) -> bytes:
    ready, _, _ = select.select([stream], [], [], timeout_sec)
    if not ready:
        raise TimeoutError("Timed out waiting for MCP server stdout.")
    return stream.readline()


def _read_exact(stream: BinaryIO, length: int, timeout_sec: float) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    deadline = time.monotonic() + timeout_sec
    while remaining > 0:
        timeout_remaining = deadline - time.monotonic()
        if timeout_remaining <= 0:
            raise TimeoutError("Timed out waiting for MCP server response body.")
        ready, _, _ = select.select([stream], [], [], timeout_remaining)
        if not ready:
            raise TimeoutError("Timed out waiting for MCP server response body.")
        chunk = os.read(stream.fileno(), remaining)
        if not chunk:
            raise RuntimeError("MCP server closed stdout while reading response body.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _read_message(stream: BinaryIO, *, timeout_sec: float, transport: str = TRANSPORT_CONTENT_LENGTH) -> dict[str, Any]:
    if transport == TRANSPORT_NEWLINE:
        line = _readline(stream, timeout_sec)
        if not line:
            raise RuntimeError("MCP server closed stdout while waiting for newline JSON response.")
        return json.loads(line.decode("utf-8"))

    headers: dict[str, str] = {}
    while True:
        line = _readline(stream, timeout_sec)
        if not line:
            raise RuntimeError("MCP server closed stdout while waiting for headers.")
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    length = int(headers.get("content-length", "0"))
    if length <= 0:
        raise RuntimeError("MCP server response did not include a positive Content-Length.")
    return json.loads(_read_exact(stream, length, timeout_sec).decode("utf-8"))


def _write_message(stream: BinaryIO, payload: dict[str, Any], *, transport: str = TRANSPORT_CONTENT_LENGTH) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if transport == TRANSPORT_NEWLINE:
        stream.write(raw + b"\n")
    else:
        stream.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        stream.write(raw)
    stream.flush()


class McpSmokeProtocol:
    """JSON-RPC stdio framing used by the MCP smoke runner."""

    def __init__(self, transport: str = TRANSPORT_CONTENT_LENGTH) -> None:
        if transport not in TRANSPORT_CHOICES:
            raise ValueError(f"Unsupported MCP smoke transport: {transport}")
        self.transport = transport

    def read(self, stream: BinaryIO, *, timeout_sec: float) -> dict[str, Any]:
        return _read_message(stream, timeout_sec=timeout_sec, transport=self.transport)

    def write(self, stream: BinaryIO, payload: dict[str, Any]) -> None:
        _write_message(stream, payload, transport=self.transport)
