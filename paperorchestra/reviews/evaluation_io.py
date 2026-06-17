from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _write_json_artifact(payload: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
