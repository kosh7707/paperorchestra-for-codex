from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


def _plain_section_title(title: str) -> str:
    match = re.fullmatch(r"\\(?:sub)*section\*?\{(.+)\}", title.strip(), flags=re.DOTALL)
    return match.group(1).strip() if match else title.strip()


def file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def _strip_latex_comments(text: str, *, preserve_numeric_percent: bool = False) -> str:
    visible_lines: list[str] = []
    for line in text.splitlines():
        comment_start = None
        backslash_run = 0
        for idx, char in enumerate(line):
            if char == "\\":
                backslash_run += 1
                continue
            if char == "%" and backslash_run % 2 == 0:
                if preserve_numeric_percent and idx > 0 and line[idx - 1].isdigit():
                    backslash_run = 0
                    continue
                comment_start = idx
                break
            backslash_run = 0
        candidate = line if comment_start is None else line[:comment_start]
        visible_lines.append(candidate.rstrip())
    return "\n".join(visible_lines)


def _planning_source_text(text: str, *, preserve_numeric_percent: bool = False) -> str:
    """Return source text suitable for claim planning and coverage terms.

    Generated smoke inputs may contain useful source comments such as
    ``% Fresh PaperOrchestra smoke input``.  Those comments are not manuscript
    claims and must not become required coverage terms or evidence anchors.
    """

    return _strip_latex_comments(text, preserve_numeric_percent=preserve_numeric_percent)


def _line_span(text: str, needle: str) -> tuple[int | None, int | None]:
    if not needle:
        return None, None
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return None, None
    return text.count("\n", 0, idx) + 1, text.count("\n", 0, idx + len(needle)) + 1


def _anchor(path: str | Path | None, excerpt: str) -> dict[str, Any]:
    text = _read_text(path)
    line_start, line_end = _line_span(text, excerpt[:80])
    return {
        "source_ref": str(path) if path else None,
        "source_sha256": file_sha256(path),
        "evidence_excerpt": excerpt[:500],
        "line_start": line_start,
        "line_end": line_end,
    }


def _salient_terms(text: str, *, limit: int = 5) -> list[str]:
    stop = {
        "the", "and", "that", "with", "from", "this", "paper", "section", "method", "result", "results",
        "using", "used", "uses", "into", "for", "are", "was", "were", "our", "their", "stated",
        "evidence", "assumptions", "construction", "benchmark", "measurement",
        "fresh", "smoke", "input", "paperorchestra", "deterministic", "derived", "registered",
        "source", "material", "materials",
    }
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+_.-]{2,}|\d+(?:\.\d+)?\s*(?:x|×|%|ms|s|jobs/s|qps)", text):
        term = token.lower().strip(" .,:;()[]{}")
        if term in stop or len(term) < 3 or term in terms:
            continue
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms
