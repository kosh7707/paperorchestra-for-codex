from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, runtime_root
from paperorchestra.loop_engine.quality.policy import HISTORY_FILENAME
from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists
from paperorchestra.loop_engine.ralph.state import QA_LOOP_HANDOFF_FILENAME


def _ralph_evidence_check(cwd: str | Path | None, *, quality_mode: str = "ralph") -> dict[str, Any]:
    handoff_path = artifact_path(cwd, QA_LOOP_HANDOFF_FILENAME)
    history_path = runtime_root(cwd) / HISTORY_FILENAME
    failing_codes = _ralph_evidence_failing_codes(handoff_path, history_path, quality_mode=quality_mode)
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "ralph_handoff": str(handoff_path),
        "ralph_handoff_sha256": _file_sha256(handoff_path),
        "qa_loop_history": str(history_path),
        "qa_loop_history_sha256": _file_sha256(history_path),
    }


def _ralph_evidence_failing_codes(handoff_path: Path, history_path: Path, *, quality_mode: str) -> list[str]:
    if quality_mode != "claim_safe":
        return []
    failing_codes = _handoff_contract_failing_codes(_read_json_if_exists(handoff_path))
    if not history_path.exists():
        failing_codes.append("qa_loop_history_missing")
    return failing_codes


def _handoff_contract_failing_codes(handoff: Any) -> list[str]:
    if not isinstance(handoff, dict):
        return ["ralph_handoff_missing"]
    contract = handoff.get("execution_contract") if isinstance(handoff.get("execution_contract"), dict) else {}
    failing_codes: list[str] = []
    if contract.get("ralph_required") is not True:
        failing_codes.append("ralph_handoff_not_required")
    if contract.get("critic_required") is not True:
        failing_codes.append("ralph_handoff_critic_not_required")
    if contract.get("citation_integrity_gate_required") is not True:
        failing_codes.append("ralph_handoff_citation_integrity_not_required")
    return failing_codes
