from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json_if_exists(path: str | Path | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))
