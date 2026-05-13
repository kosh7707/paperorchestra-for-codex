from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEXT_EXTENSIONS = {".tex", ".bib", ".md", ".txt", ".rst", ".csv", ".json", ".yaml", ".yml"}
FIGURE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".svg"}


@dataclass(frozen=True)
class MaterialFile:
    path_label: str
    path_sha256: str
    extension: str
    role: str
    bytes: int
    sha256: str

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class MaterialInventory:
    schema_version: str
    file_count: int
    total_bytes: int
    role_counts: dict[str, int]
    extension_counts: dict[str, int]
    files: list[MaterialFile] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "role_counts": dict(self.role_counts),
            "extension_counts": dict(self.extension_counts),
            "files": [item.to_public_dict() for item in self.files],
            "private_safe_summary": self.private_safe_summary,
        }


@dataclass(frozen=True)
class SourceDigest:
    schema_version: str
    status: str
    sufficient: bool
    file_count: int
    source_like_file_count: int
    role_counts: dict[str, int]
    extension_counts: dict[str, int]
    total_bytes: int
    blocking_reasons: list[str] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _role_for(path: Path) -> str:
    suffix = path.suffix.lower()
    stem = path.stem.lower()
    if suffix == ".tex":
        return "manuscript_tex"
    if suffix == ".bib":
        return "bibtex"
    if suffix in FIGURE_EXTENSIONS:
        return "figure_asset"
    if suffix in {".md", ".txt", ".rst"}:
        if any(term in stem for term in ["experiment", "result", "log", "benchmark"]):
            return "experiment_or_results"
        if any(term in stem for term in ["guideline", "venue", "conference"]):
            return "venue_or_guidelines"
        return "idea_or_notes"
    if suffix in TEXT_EXTENSIONS:
        return "other_text"
    return "other_binary"


def build_material_inventory(path: str | Path) -> MaterialInventory:
    root = Path(path).resolve()
    candidates = [root] if root.is_file() else sorted(item for item in root.rglob("*") if item.is_file())
    files: list[MaterialFile] = []
    role_counts: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    total_bytes = 0
    for file_path in candidates:
        try:
            data = file_path.read_bytes()
        except OSError:
            continue
        suffix = file_path.suffix.lower() or "<none>"
        role = _role_for(file_path)
        path_hash = _sha256_text(str(file_path.relative_to(root) if root.is_dir() else file_path.name))
        digest = _sha256_bytes(data)
        total_bytes += len(data)
        role_counts[role] += 1
        extension_counts[suffix] += 1
        files.append(
            MaterialFile(
                path_label=f"redacted-material:{path_hash[:12]}",
                path_sha256=path_hash,
                extension=suffix,
                role=role,
                bytes=len(data),
                sha256=digest,
            )
        )
    return MaterialInventory(
        schema_version="material-inventory/1",
        file_count=len(files),
        total_bytes=total_bytes,
        role_counts=dict(sorted(role_counts.items())),
        extension_counts=dict(sorted(extension_counts.items())),
        files=files,
    )


def build_source_digest(inventory: MaterialInventory) -> SourceDigest:
    source_roles = {
        "manuscript_tex",
        "bibtex",
        "idea_or_notes",
        "experiment_or_results",
        "venue_or_guidelines",
        "other_text",
    }
    source_like = sum(inventory.role_counts.get(role, 0) for role in source_roles)
    has_manuscript_plus_support = inventory.role_counts.get("manuscript_tex", 0) >= 1 and source_like >= 2
    sufficient = source_like >= 2 and (has_manuscript_plus_support or inventory.total_bytes >= 32)
    blockers: list[str] = []
    if not sufficient:
        blockers.append("insufficient_material")
    return SourceDigest(
        schema_version="source-digest/1",
        status="ready" if sufficient else "insufficient",
        sufficient=sufficient,
        file_count=inventory.file_count,
        source_like_file_count=source_like,
        role_counts=dict(inventory.role_counts),
        extension_counts=dict(inventory.extension_counts),
        total_bytes=inventory.total_bytes,
        blocking_reasons=blockers,
    )
