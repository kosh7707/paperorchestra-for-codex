from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .io_utils import read_json, write_json
from .domains import detect_domain_for_text, get_domain
from .models import utc_now_iso
from .session import artifact_path, load_session, save_session
from .validator import extract_decimal_like_tokens

SOURCE_OBLIGATIONS_SCHEMA_VERSION = "source-obligations/1"

SOURCE_FIELDS = (
    ("idea", "idea_path"),
    ("experimental_log", "experimental_log_path"),
    ("template", "template_path"),
    ("guidelines", "guidelines_path"),
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


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", normalized)
    return [part.strip() for part in parts if len(part.strip()) >= 20]


def _best_excerpt(text: str, pattern: re.Pattern[str]) -> str:
    for sentence in _sentences(text):
        if pattern.search(sentence):
            return sentence[:700]
    match = pattern.search(text)
    if not match:
        return text[:300]
    start = max(match.start() - 180, 0)
    end = min(match.end() + 420, len(text))
    return re.sub(r"\s+", " ", text[start:end]).strip()


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


def build_source_obligations(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    source_entries, packet_digest, texts = _source_packet(cwd)
    obligations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for label, text in texts.items():
        if not text.strip():
            continue
        domain = detect_domain_for_text(text)
        for obligation_type, raw_pattern, seed_terms in domain.obligation_patterns:
            pattern = re.compile(raw_pattern, re.IGNORECASE)
            if not pattern.search(text):
                continue
            excerpt = _best_excerpt(text, pattern)
            if label == "template" and _substantive_word_count(excerpt) < 8:
                continue
            key = (obligation_type, _sha256_text(excerpt)[:16])
            if key in seen:
                continue
            seen.add(key)
            numeric_tokens = sorted(extract_decimal_like_tokens(excerpt))
            obligation_id = f"obl-{len(obligations)+1:03d}-{obligation_type}"
            obligations.append(
                {
                    "id": obligation_id,
                    "type": obligation_type,
                    "source_label": label,
                    "source_path": getattr(state.inputs, f"{label}_path", None) if label != "experimental_log" else state.inputs.experimental_log_path,
                    "source_packet_sha256": packet_digest,
                    "excerpt_sha256": _sha256_text(excerpt),
                    "excerpt_preview": excerpt[:240],
                    "required_terms": _terms(excerpt, seed_terms),
                    "numeric_tokens": numeric_tokens,
                    "expected_manuscript_area": _expected_area(obligation_type),
                }
            )
    return {
        "schema_version": SOURCE_OBLIGATIONS_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": state.session_id,
        "source_packet_sha256": packet_digest,
        "source_files": source_entries,
        "generator": {
            "name": "paperorchestra.deterministic_source_obligations",
            "version": 1,
            "model_used": False,
        },
        "obligations": obligations,
    }


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


def source_obligations_path(cwd: str | Path | None) -> Path:
    state = load_session(cwd)
    if getattr(state.artifacts, "source_obligations_json", None):
        return Path(state.artifacts.source_obligations_json)
    return artifact_path(cwd, "source_obligations.json")


def write_source_obligations(cwd: str | Path | None, output_path: str | Path | None = None) -> Path:
    payload = build_source_obligations(cwd)
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "source_obligations.json")
    write_json(path, payload)
    state = load_session(cwd)
    state.artifacts.source_obligations_json = str(path)
    state.notes.append(f"Source obligations recorded: {path.name}")
    save_session(cwd, state)
    return path


def _load_obligations(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def evaluate_source_obligations(cwd: str | Path | None, manuscript_text: str | None = None) -> dict[str, Any]:
    state = load_session(cwd)
    path = source_obligations_path(cwd)
    payload = _load_obligations(path)
    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "path": str(path),
            "failing_codes": ["source_obligations_missing"],
            "obligations_checked": 0,
            "unsatisfied": [],
        }
    source_entries, packet_digest, _ = _source_packet(cwd)
    failing_codes: list[str] = []
    if payload.get("schema_version") != SOURCE_OBLIGATIONS_SCHEMA_VERSION:
        failing_codes.append("source_obligations_legacy_untrusted")
    if payload.get("source_packet_sha256") != packet_digest:
        failing_codes.append("source_obligations_stale")
    obligations = payload.get("obligations") if isinstance(payload.get("obligations"), list) else []
    if manuscript_text is None:
        manuscript_text = _read(state.artifacts.paper_full_tex)
    lowered = manuscript_text.lower()
    present_numbers = extract_decimal_like_tokens(manuscript_text)
    unsatisfied: list[dict[str, Any]] = []
    for obligation in obligations:
        if not isinstance(obligation, dict):
            continue
        required_terms = [str(term).lower() for term in obligation.get("required_terms") or [] if str(term).strip()]
        numeric_tokens = set(str(token) for token in obligation.get("numeric_tokens") or [])
        matched_terms = [term for term in required_terms if term in lowered]
        required_min = min(len(required_terms), max(1, 2 if len(required_terms) >= 3 else len(required_terms)))
        missing_terms = len(matched_terms) < required_min
        missing_numbers = obligation.get("type") == "benchmark_result" and bool(numeric_tokens) and not bool(numeric_tokens & present_numbers)
        if missing_terms or missing_numbers:
            codes = []
            if missing_terms:
                codes.append("source_obligation_anchor_missing")
            if missing_numbers:
                codes.append("source_obligation_numeric_mismatch")
            unsatisfied.append(
                {
                    "id": obligation.get("id"),
                    "type": obligation.get("type"),
                    "expected_manuscript_area": obligation.get("expected_manuscript_area"),
                    "matched_terms": matched_terms,
                    "required_terms": required_terms,
                    "numeric_tokens": sorted(numeric_tokens),
                    "codes": codes,
                }
            )
    if unsatisfied:
        failing_codes.append("source_obligation_missing")
        if any("source_obligation_anchor_missing" in item["codes"] for item in unsatisfied):
            failing_codes.append("source_obligation_anchor_missing")
        if any("source_obligation_numeric_mismatch" in item["codes"] for item in unsatisfied):
            failing_codes.append("source_obligation_numeric_mismatch")
    return {
        "status": "fail" if failing_codes else "pass",
        "path": str(path),
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "source_packet_sha256": payload.get("source_packet_sha256"),
        "expected_source_packet_sha256": packet_digest,
        "source_files": source_entries,
        "obligations_checked": len([item for item in obligations if isinstance(item, dict)]),
        "unsatisfied": unsatisfied,
    }
