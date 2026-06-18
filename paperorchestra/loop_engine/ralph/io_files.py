from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any


def _read_json(path: str | Path | None) -> Any:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return json.loads(candidate.read_text(encoding="utf-8"))


def _artifact_sha(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()


def _text_sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    try:
        tmp_path.write_text(text, encoding=encoding)
        os.replace(tmp_path, destination)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _file_content_snapshot(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"path": None, "exists": False, "content": None}
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return {"path": str(candidate), "exists": False, "content": None}
    return {"path": str(candidate), "exists": True, "content": candidate.read_bytes()}


def _restore_file_content_snapshot(snapshot: dict[str, Any]) -> None:
    path_value = snapshot.get("path")
    if not path_value:
        return
    path = Path(path_value)
    if snapshot.get("exists"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(snapshot.get("content") or b"")
    elif path.exists():
        path.unlink()
