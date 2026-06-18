from __future__ import annotations

from pathlib import Path
from typing import Any


def missing_v3_pass_evidence_count(cases: list[dict[str, Any]], run_root: Path) -> int:
    return sum(1 for case in cases if _pass_case_lacks_source_artifact(case, run_root))


def _pass_case_lacks_source_artifact(case: dict[str, Any], run_root: Path) -> bool:
    if str(case.get("verdict") or "human_needed") != "pass":
        return False
    evidence = case.get("evidence") if isinstance(case.get("evidence"), dict) else {}
    if str(evidence.get("status") or "missing") not in {"pdf", "html", "text"}:
        return True
    return not _evidence_text_ready(evidence.get("text"), run_root)


def _evidence_text_ready(value: Any, run_root: Path) -> bool:
    if not value:
        return False
    path = Path(str(value))
    if not path.is_absolute():
        path = run_root / path
    try:
        return path.exists() and path.is_file() and path.stat().st_size > 0
    except OSError:
        return False
