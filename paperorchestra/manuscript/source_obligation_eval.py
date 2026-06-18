from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.manuscript.source_obligation_build import SOURCE_OBLIGATIONS_SCHEMA_VERSION, build_source_obligations
from paperorchestra.manuscript.source_obligation_extraction import _read, _source_packet
from paperorchestra.manuscript.validator import extract_decimal_like_tokens


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
