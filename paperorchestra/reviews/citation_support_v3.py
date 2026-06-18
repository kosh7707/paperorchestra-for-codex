from __future__ import annotations

from pathlib import Path
from typing import Any


def _support_items_from_v3_cases(cases: Any, *, run_root: Path | None = None) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        return []
    items: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        key = str(case.get("key") or "").strip()
        if not key:
            continue
        evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
        items.append(
            {
                "id": str(case.get("id") or f"case-{len(items) + 1}"),
                "sentence": None,
                "citation_keys": [key],
                "support_status": _v3_support_status(case.get("verdict"), evidence, run_root=run_root),
                "claim_type": None,
                "evidence": [] if evidence.get("status") in {"missing", "blocked"} else [evidence],
            }
        )
    return items


def _v3_support_status(verdict: Any, evidence: dict[str, Any], *, run_root: Path | None = None) -> str:
    status = str(evidence.get("status") or "missing").strip().lower() or "missing"
    normalized = str(verdict or "human_needed").strip().lower() or "human_needed"
    if normalized == "pass":
        evidence_readable = _v3_evidence_text_readable(evidence, run_root=run_root)
        return "supported" if status in {"pdf", "html", "text"} and evidence_readable else "insufficient_evidence"
    if normalized == "weak":
        return "metadata_only"
    if normalized == "fail":
        return "unsupported"
    if normalized == "human_needed":
        return "insufficient_evidence"
    return "unknown"


def _v3_evidence_text_readable(evidence: dict[str, Any], *, run_root: Path | None = None) -> bool:
    values = [evidence.get("text")]
    if str(evidence.get("status") or "").strip().lower() == "text":
        values.append(evidence.get("path"))
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        path = Path(value)
        if not path.is_absolute() and run_root is not None:
            path = run_root / path
        try:
            if path.exists() and path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False
