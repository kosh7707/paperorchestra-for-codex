from __future__ import annotations

import json
from pathlib import Path


def record_provider_retry_attempt(trace_dir: Path | None, payload: dict[str, object]) -> None:
    if trace_dir is None:
        return
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / "provider-retry-attempts.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")
