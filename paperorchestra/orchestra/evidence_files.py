from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

DEFAULT_EVIDENCE_DIR = Path(".paper-orchestra") / "orchestrator-evidence"


def resolve_bundle_dir(root: Path, output_dir: str | Path | None) -> Path:
    if output_dir is None:
        candidate = root / DEFAULT_EVIDENCE_DIR
    else:
        candidate = Path(output_dir).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("Evidence output must stay under the current workspace.")
    return resolved


def remove_stale_evidence_files(evidence_dir: Path) -> None:
    for path in evidence_dir.glob("*.json"):
        path.unlink()
    for path in evidence_dir.iterdir():
        if path.is_dir():
            shutil.rmtree(path)


def write_json_with_sha(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify_evidence_kind(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return slug or "evidence"


def relative_to_bundle(path: Path, bundle_dir: Path) -> str:
    return path.relative_to(bundle_dir).as_posix()


__all__ = [
    "DEFAULT_EVIDENCE_DIR",
    "relative_to_bundle",
    "remove_stale_evidence_files",
    "resolve_bundle_dir",
    "sha256_file",
    "slugify_evidence_kind",
    "write_json_with_sha",
]
