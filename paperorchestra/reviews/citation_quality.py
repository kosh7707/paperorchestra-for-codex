from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.reviews.citation_quality_builder import (
    _normalize_quality_mode,
    _stale_codes,
    build_citation_quality_gate,
    build_citation_quality_gate_internal,
)
from paperorchestra.reviews.citation_quality_paths import (
    CITATION_QUALITY_GATE_FILENAME,
    CITATION_QUALITY_GATE_INTERNAL_FILENAME,
    citation_quality_gate_internal_path,
    citation_quality_gate_path,
)


def write_citation_quality_gate(
    cwd: str | Path | None,
    *,
    quality_mode: str = "ralph",
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    internal_payload = build_citation_quality_gate_internal(cwd, quality_mode=quality_mode)
    payload = internal_payload["public_report"]
    canonical_path = citation_quality_gate_path(cwd)
    path = Path(output_path).resolve() if output_path else canonical_path
    write_json(path, payload)
    if path.resolve() == canonical_path.resolve():
        write_json(citation_quality_gate_internal_path(cwd), internal_payload)
    return path, payload


__all__ = [
    "CITATION_QUALITY_GATE_FILENAME",
    "CITATION_QUALITY_GATE_INTERNAL_FILENAME",
    "_normalize_quality_mode",
    "_stale_codes",
    "build_citation_quality_gate",
    "build_citation_quality_gate_internal",
    "citation_quality_gate_internal_path",
    "citation_quality_gate_path",
    "write_citation_quality_gate",
]
