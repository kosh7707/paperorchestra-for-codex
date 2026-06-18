from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paperorchestra.runtime.providers import BaseProvider


@dataclass(frozen=True)
class QaLoopActionDispatchContext:
    cwd: str | Path | None
    provider: BaseProvider
    runtime_mode: str
    require_compile: bool
    quality_mode: str
    citation_evidence_mode: str
    citation_provider: BaseProvider | None
    paper_path: Path | None
    original_paper: str | None


@dataclass(frozen=True)
class QaLoopActionDispatchResult:
    citation_candidate_applied: bool
    citation_candidate_path: str | None


@dataclass
class _QaLoopActionDispatchState:
    citation_candidate_applied: bool = False
    citation_candidate_path: str | None = None
