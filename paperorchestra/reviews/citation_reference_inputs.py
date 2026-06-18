from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _read_json_if_exists
from paperorchestra.manuscript.citations import extract_citation_keys


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def _bib_entries(text: str) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for match in re.finditer(r"@(\w+)\s*\{\s*([^,]+)\s*,(.*?)(?=\n@\w+\s*\{|\Z)", text, re.DOTALL):
        key = match.group(2).strip()
        body = match.group(3)
        fields: dict[str, Any] = {"entry_type": match.group(1).strip().lower()}
        for field_match in re.finditer(
            r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)",
            body,
            re.DOTALL,
        ):
            raw = field_match.group(2).strip().rstrip(",")
            if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith('"') and raw.endswith('"')):
                raw = raw[1:-1]
            fields[field_match.group(1).strip().lower()] = re.sub(r"\s+", " ", raw).strip()
        entries[key] = fields
    return entries


def _bbl_visible_keys(path: Path) -> list[str]:
    text = _read_text(path)
    return [match.group(1).strip() for match in re.finditer(r"\\bibitem(?:\[[^]]*\])?\{([^}]+)\}", text)]


def _candidate_bbl_paths(state: Any) -> list[Path]:
    candidates: list[Path] = []
    if state.artifacts.paper_full_tex:
        paper = Path(state.artifacts.paper_full_tex)
        candidates.append(paper.with_suffix(".bbl"))
    compile_report = _read_json_if_exists(state.artifacts.latest_compile_report_json)
    if isinstance(compile_report, dict):
        pdf_path = compile_report.get("pdf_path")
        if isinstance(pdf_path, str):
            candidates.append(Path(pdf_path).with_suffix(".bbl"))
    seen: set[Path] = set()
    result: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if resolved not in seen:
            seen.add(resolved)
            result.append(candidate)
    return result


def _visible_reference_keys(state: Any) -> tuple[str, list[str]]:
    for path in _candidate_bbl_paths(state):
        if path.exists():
            keys = _bbl_visible_keys(path)
            if keys:
                return "bbl_bibitems", keys
    latex = _read_text(state.artifacts.paper_full_tex)
    return "tex_cited_keys_fallback", sorted(extract_citation_keys(latex))
