from __future__ import annotations

import re
import shutil
from pathlib import Path

from paperorchestra.manuscript.latex_input_roots import _infer_project_root_from_source


def _prepare_compile_inputs(source_path: Path, workdir_path: Path) -> None:
    references_source = source_path.parent / "references.bib"
    if references_source.exists():
        shutil.copy2(references_source, workdir_path / "references.bib")


def _referenced_bibliography_stems(source_text: str) -> list[str]:
    stems: list[str] = []
    for raw_group in re.findall(r"\\bibliography\s*\{([^}]+)\}", source_text):
        for raw_stem in raw_group.split(","):
            stem = raw_stem.strip()
            if stem and stem not in stems:
                stems.append(stem)
    return stems


def _is_relative_bibliography_path_safe(raw_stem: str) -> bool:
    raw_path = Path(raw_stem)
    return bool(raw_stem) and not raw_path.is_absolute() and ".." not in raw_path.parts


def _is_regular_file_within_root(candidate: Path, base: Path) -> bool:
    if candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
        return False
    try:
        relative_parts = candidate.relative_to(base).parts
    except ValueError:
        return False
    current = base
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            return False
    try:
        candidate.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _copy_bibliography_input_files(
    *,
    bibliography_stems: list[str],
    source_path: Path,
    run_root: Path,
    workdir_path: Path,
) -> None:
    search_roots = [source_path.parent, run_root]
    project_root = _infer_project_root_from_source(source_path)
    if project_root not in search_roots:
        search_roots.append(project_root)
    for raw_stem in bibliography_stems:
        if not _is_relative_bibliography_path_safe(raw_stem):
            continue
        candidate_rel = Path(f"{raw_stem}.bib")
        for base in search_roots:
            candidate = base / candidate_rel
            if _is_regular_file_within_root(candidate, base):
                destination = workdir_path / candidate_rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)
                break
