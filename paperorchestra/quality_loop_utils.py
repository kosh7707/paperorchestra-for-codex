from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .io_utils import read_json

def _read_json_if_exists(path: str | Path | None) -> Any | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        return read_json(candidate)
    except Exception:
        return None


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _sha256_jsonable(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_ref(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return str(candidate)
    return f"{candidate}@sha256:{_file_sha256(candidate)}"

