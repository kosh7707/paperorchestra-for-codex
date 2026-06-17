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
    handoff = _read_json_if_exists(handoff_path)
    failing_codes: list[str] = []
    if quality_mode == "claim_safe":
        if not isinstance(handoff, dict):
            failing_codes.append("ralph_handoff_missing")
        else:
            contract = handoff.get("execution_contract") if isinstance(handoff.get("execution_contract"), dict) else {}
            if contract.get("ralph_required") is not True:
                failing_codes.append("ralph_handoff_not_required")
            if contract.get("critic_required") is not True:
                failing_codes.append("ralph_handoff_critic_not_required")
            if contract.get("citation_integrity_gate_required") is not True:
                failing_codes.append("ralph_handoff_citation_integrity_not_required")
        if not history_path.exists():
            failing_codes.append("qa_loop_history_missing")
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "ralph_handoff": str(handoff_path),
        "ralph_handoff_sha256": _file_sha256(handoff_path),
        "qa_loop_history": str(history_path),
        "qa_loop_history_sha256": _file_sha256(history_path),
    }


def _figure_grounding_check(state: Any) -> dict[str, Any]:
    path = state.artifacts.latest_figure_placement_review_json
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "status": "skipped",
            "reason": "figure_placement_review_missing_or_unreadable",
            "failing_codes": [],
            "warning_codes": [],
        }
    expected_manuscript_sha = _file_sha256(getattr(state.artifacts, "paper_full_tex", None))
    actual_manuscript_sha = str(payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256") or "").strip()
    if actual_manuscript_sha.startswith("sha256:"):
        actual_manuscript_sha = actual_manuscript_sha.split("sha256:", 1)[1]
    if expected_manuscript_sha and not actual_manuscript_sha:
        return {
            "status": "fail",
            "failing_codes": ["figure_placement_review_unbound"],
            "warning_codes": [],
            "path": path,
            "expected_manuscript_sha256": expected_manuscript_sha,
            "artifact_status": str(payload.get("status") or "unknown").strip().lower(),
        }
    if expected_manuscript_sha and actual_manuscript_sha != expected_manuscript_sha:
        return {
            "status": "fail",
            "failing_codes": ["figure_placement_review_stale"],
            "warning_codes": [],
            "path": path,
            "expected_manuscript_sha256": expected_manuscript_sha,
            "actual_manuscript_sha256": actual_manuscript_sha,
            "artifact_status": str(payload.get("status") or "unknown").strip().lower(),
        }
    status = str(payload.get("status") or "pass").strip().lower()
    failing_codes = sorted(dict.fromkeys(str(code) for code in payload.get("failing_codes") or [] if str(code).strip()))
    warning_codes = sorted(dict.fromkeys(str(code) for code in payload.get("warning_codes") or [] if str(code).strip()))
    issue_figures = [
        {
            "label": str(item.get("label") or ""),
            "section_title": str(item.get("section_title") or ""),
            "failing_codes": [str(code) for code in item.get("failing_codes") or [] if str(code).strip()],
            "warning_codes": [str(code) for code in item.get("warning_codes") or [] if str(code).strip()],
            "included_assets": [str(asset) for asset in item.get("included_assets") or [] if str(asset).strip()],
            "nearby_reference_context": str(item.get("nearby_reference_context") or "")[:500],
            "plot_manifest_match": item.get("plot_manifest_match") if isinstance(item.get("plot_manifest_match"), dict) else None,
        }
        for item in payload.get("figures") or []
        if isinstance(item, dict) and (item.get("failing_codes") or item.get("warning_codes"))
    ]
    return {
        "status": "fail"
        if failing_codes or status in {"fail", "failed", "block", "blocked"}
        else "warn"
        if warning_codes or status in {"warn", "warning"}
        else "pass",
        "failing_codes": failing_codes,
        "warning_codes": warning_codes,
        "path": path,
        "artifact_status": status,
        "figures": issue_figures,
    }
