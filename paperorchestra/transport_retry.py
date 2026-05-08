from __future__ import annotations

import argparse
import re
from pathlib import Path

TRANSIENT_TRANSPORT_PATTERNS: tuple[str, ...] = (
    r"\breconnecting\b",
    r"connection (?:lost|closed|reset|timed out|timeout|error)",
    r"network (?:error|timeout|failure)",
    r"stream (?:disconnected|closed|interrupted)",
    r"\b(?:ECONNRESET|ETIMEDOUT|ENETDOWN|ENETUNREACH|EAI_AGAIN)\b",
    r"temporarily unavailable",
    r"upstream (?:timeout|unavailable|disconnected)",
)

_TRANSIENT_TRANSPORT_REGEXES = tuple(re.compile(pattern, re.IGNORECASE) for pattern in TRANSIENT_TRANSPORT_PATTERNS)


def is_retryable_transport_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in _TRANSIENT_TRANSPORT_REGEXES)


def is_retryable_transport_file(path: str | Path) -> bool:
    candidate = Path(path)
    if not candidate.is_file():
        return False
    return is_retryable_transport_text(candidate.read_text(encoding="utf-8", errors="replace"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect retryable Codex/OMX transport stderr patterns.")
    parser.add_argument("--file", required=True, help="stderr/log file to scan")
    args = parser.parse_args(argv)
    return 0 if is_retryable_transport_file(args.file) else 1


if __name__ == "__main__":  # pragma: no cover - exercised by shell scripts
    raise SystemExit(main())
