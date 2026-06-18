from __future__ import annotations

import sys
from typing import Any, Callable


def _handler_dependency(name: str, default: Callable[..., Any]) -> Callable[..., Any]:
    handlers = sys.modules.get("paperorchestra.loop_engine.ralph.action_dispatch_handlers")
    if handlers is None:
        return default
    return getattr(handlers, name, default)
