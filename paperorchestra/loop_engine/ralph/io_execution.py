from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.session import runtime_root


@dataclass(frozen=True)
class StepResult:
    path: Path
    payload: dict[str, Any]
    exit_code: int


def _next_execution_path(cwd: str | Path | None) -> tuple[int, Path]:
    root = runtime_root(cwd)
    existing = sorted(root.glob("qa-loop-execution.iter-*.json"))
    index = len(existing) + 1
    return index, root / f"qa-loop-execution.iter-{index:02d}.json"
