from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CitationWriteCacheState:
    cache_key: str | None = None
    cache_payload_path: Path | None = None
    cache_trace_path: Path | None = None
    retrieved_web_evidence: dict[str, Any] | None = None
    retrieved_web_evidence_path: Path | None = None
    retrieved_web_evidence_sha256: str | None = None
    citation_review_cacheable: bool = True
