from __future__ import annotations

import hashlib
from pathlib import Path

REFERENCE_SEED_EXTENSIONS = {".bib", ".bibtex"}


def _seed_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in REFERENCE_SEED_EXTENSIONS else []
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in REFERENCE_SEED_EXTENSIONS)


def _relative_label(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)) if root.is_dir() else path.name
    except ValueError:
        return path.name


def _redacted_seed_label(path: Path, root: Path) -> str:
    return f"redacted-reference-seed:{_sha256_text(_relative_label(path, root))[:12]}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
