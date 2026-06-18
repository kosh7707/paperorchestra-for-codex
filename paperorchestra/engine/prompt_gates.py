from __future__ import annotations

from paperorchestra.engine.completion import _env_flag


def _strict_content_gates_enabled(*, claim_safe: bool = False) -> bool:
    return claim_safe or _env_flag("PAPERO_STRICT_CONTENT_GATES")
