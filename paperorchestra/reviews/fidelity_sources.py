from __future__ import annotations

import os
from pathlib import Path

from paperorchestra.manuscript import prompts as prompt_module

PAPER_SOURCE_NAME = "PaperOrchestra A Multi-Agent Framework for Automated AI Research Paper Writing.pdf"
PAPER_SOURCE_ENV_VAR = "PAPERO_REFERENCE_PDF"


def paper_source_candidates(cwd: str | Path | None) -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get(PAPER_SOURCE_ENV_VAR)
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())
    if cwd is not None:
        candidates.append(Path(cwd).resolve() / PAPER_SOURCE_NAME)
    repo_root = Path(prompt_module.__file__).resolve().parent.parent
    candidates.append(repo_root / PAPER_SOURCE_NAME)
    return candidates
