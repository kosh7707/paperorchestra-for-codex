from __future__ import annotations

import sys
from typing import Any, Callable


def _outcome_dependency(name: str, default: Callable[..., Any]) -> Callable[..., Any]:
    outcomes = sys.modules.get("paperorchestra.engine.refine_iteration_outcomes")
    if outcomes is None:
        return default
    return getattr(outcomes, name, default)
