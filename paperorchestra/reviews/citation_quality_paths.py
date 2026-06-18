from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import artifact_path

CITATION_QUALITY_GATE_FILENAME = "citation_quality_gate.json"
CITATION_QUALITY_GATE_INTERNAL_FILENAME = "citation_quality_gate.internal.json"


def citation_quality_gate_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_QUALITY_GATE_FILENAME)


def citation_quality_gate_internal_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_QUALITY_GATE_INTERNAL_FILENAME)
