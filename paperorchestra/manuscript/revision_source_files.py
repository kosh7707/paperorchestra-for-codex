from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _section_files(source_paper: Path) -> dict[str, str]:
    text = source_paper.read_text(encoding="utf-8", errors="replace")
    root = source_paper.parent
    mapping: dict[str, str] = {}
    for include in re.findall(r"\\(?:input|include)\{([^}]+)\}", text):
        path = (root / include).with_suffix(".tex") if not include.endswith(".tex") else root / include
        key = path.stem.lower()
        if "intro" in key or "related" in key:
            mapping.setdefault("introduction_related_work", str(path))
        if "method" in key or "proposed" in key:
            mapping.setdefault("proposed_method", str(path))
        if "security" in key:
            mapping.setdefault("security_analysis", str(path))
        if "implementation" in key or "result" in key or "experiment" in key:
            mapping.setdefault("implementation_results", str(path))
        if "discussion" in key or "conclusion" in key:
            mapping.setdefault("discussion_limitations", str(path))
    return mapping


def _section_diagnostics(section_map: dict[str, str]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for area, filename in section_map.items():
        path = Path(filename)
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        diagnostics[area] = {
            "file": filename,
            "exists": path.exists(),
            "word_count": len(re.findall(r"\w+", text)),
            "citation_count": len(re.findall(r"\\cite\{", text)),
            "todo_markers": len(re.findall(r"TODO|TBD|\\todo", text, flags=re.IGNORECASE)),
        }
    return diagnostics


def _load_optional_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        return {}
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}
