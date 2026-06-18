from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.domains import detect_domain_for_text, get_domain

SOURCE_FIELDS = (
    ("idea", "idea_path"),
    ("experimental_log", "experimental_log_path"),
    ("template", "template_path"),
    ("guidelines", "guidelines_path"),
)

OBLIGATION_SOURCE_LABELS = {"idea", "experimental_log"}

SOURCE_OBLIGATION_META_SECTION_RE = re.compile(
    r"^(?:author intent|non-negotiable claim boundaries|author positioning notes|writing contract|fresh paperorchestra smoke input)\b",
    re.IGNORECASE,
)

OBLIGATION_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = get_domain().obligation_patterns
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+_.-]{2,}|\d+(?:\.\d+)?\s*[x×%]?")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def _read(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def _source_packet(cwd: str | Path | None) -> tuple[list[dict[str, Any]], str, dict[str, str]]:
    state = load_session(cwd)
    entries: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    for label, field_name in SOURCE_FIELDS:
        path = getattr(state.inputs, field_name)
        text = _read(path)
        texts[label] = text
        entries.append(
            {
                "label": label,
                "path": path,
                "sha256": _file_sha256(path),
                "bytes": len(text.encode("utf-8")),
            }
        )
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return entries, digest, texts


def _strip_latex_heading_prefix(text: str) -> str:
    return re.sub(r"^\s*\\(?:sub)*section\*?\{([^}]*)\}\s*", r"\1. ", text).strip()


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"(?m)^%.*$", " ", text)
    normalized = re.sub(r"\\label\{[^}]*\}", " ", normalized)
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", normalized)
    result: list[str] = []
    for part in parts:
        part = re.sub(r"\s+", " ", _strip_latex_heading_prefix(part)).strip()
        if len(part) >= 20:
            result.append(part)
    return result


def _is_meta_or_template_excerpt(label: str, excerpt: str) -> bool:
    lowered = excerpt.strip().lower()
    if label not in OBLIGATION_SOURCE_LABELS:
        return True
    if SOURCE_OBLIGATION_META_SECTION_RE.search(lowered):
        return True
    if "documentclass" in lowered or "usepackage" in lowered or "begin{document}" in lowered:
        return True
    if "fresh paperorchestra smoke input" in lowered:
        return True
    return False


def _candidate_excerpts(label: str, text: str, pattern: re.Pattern[str]) -> list[str]:
    excerpts: list[str] = []
    seen: set[str] = set()
    for sentence in _sentences(text):
        if not pattern.search(sentence):
            continue
        excerpt = sentence[:700]
        if _is_meta_or_template_excerpt(label, excerpt):
            continue
        key = _sha256_text(excerpt)[:16]
        if key not in seen:
            excerpts.append(excerpt)
            seen.add(key)
    if excerpts:
        return excerpts
    match = pattern.search(text)
    if not match:
        return []
    start = max(match.start() - 180, 0)
    end = min(match.end() + 420, len(text))
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    return [] if _is_meta_or_template_excerpt(label, excerpt) else [excerpt]


def _substantive_word_count(text: str) -> int:
    without_commands = re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})?", " ", text)
    return len(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", without_commands))


def _terms(excerpt: str, seed_terms: tuple[str, ...]) -> list[str]:
    tokens = [token.lower().strip(" .,:;()[]{}") for token in TOKEN_RE.findall(excerpt)]
    stop = {
        "the", "and", "that", "with", "from", "this", "into", "paper", "section", "result", "results",
        "method", "proof", "show", "shows", "using", "used", "where", "which", "their", "there",
    }
    scored: list[str] = []
    for term in list(seed_terms) + tokens:
        term = term.lower().strip()
        if len(term) < 3 or term in stop:
            continue
        if term not in scored:
            scored.append(term)
        if len(scored) >= 8:
            break
    return scored


def _expected_area(obligation_type: str) -> str:
    return {
        "method_core": "method",
        "security_assumption": "security_or_method",
        "theorem_or_bound": "security_analysis",
        "proof_step": "security_analysis",
        "benchmark_setup": "experiments",
        "benchmark_result": "experiments_or_results",
        "limitation_or_scope": "discussion_or_limitations",
    }.get(obligation_type, "manuscript")


def obligation_domains_for_text(text: str):
    return detect_domain_for_text(text)
