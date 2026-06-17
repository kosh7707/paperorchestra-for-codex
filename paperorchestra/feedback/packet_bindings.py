from __future__ import annotations

import hashlib
import json
from typing import Any

from paperorchestra.core.io import read_json


def _normalized_sha(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.split("sha256:", 1)[1] if text.startswith("sha256:") else text


def _artifact_payload(record: dict[str, Any]) -> dict[str, Any] | None:
    try:
        payload = read_json(record["path"])
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _artifact_bound_manuscript_sha(role: str, payload: dict[str, Any]) -> str | None:
    if role in {
        "citation_support_review",
        "section_review",
        "citation_integrity_audit",
        "citation_integrity_critic",
        "figure_placement_review",
    }:
        return _normalized_sha(payload.get("manuscript_sha256"))
    if role == "quality_eval":
        return _normalized_sha(payload.get("manuscript_hash"))
    if role == "qa_loop_plan":
        summary = payload.get("quality_eval_summary") if isinstance(payload.get("quality_eval_summary"), dict) else {}
        return _normalized_sha(summary.get("manuscript_hash"))
    if role == "qa_loop_execution":
        progress = payload.get("progress") if isinstance(payload.get("progress"), dict) else {}
        restored_state = payload.get("restored_current_state") if isinstance(payload.get("restored_current_state"), dict) else {}
        restored_progress = restored_state.get("progress") if isinstance(restored_state.get("progress"), dict) else {}
        return _normalized_sha(
            payload.get("manuscript_sha256_before")
            or (payload.get("candidate_approval") or {}).get("base_manuscript_sha256")
            or progress.get("before_manuscript_hash")
            or restored_progress.get("before_manuscript_hash")
        )
    if role == "operator_feedback_execution":
        return _normalized_sha(
            payload.get("manuscript_sha256_before")
            or (payload.get("candidate_approval") or {}).get("base_manuscript_sha256")
            or ((payload.get("candidate_result") or {}).get("candidate_approval") or {}).get("base_manuscript_sha256")
        )
    return None


def _execution_payload_sha256(execution: dict[str, Any]) -> str:
    payload_for_hash = json.loads(json.dumps(execution, sort_keys=True))
    approval = payload_for_hash.get("candidate_approval")
    if isinstance(approval, dict):
        approval.pop("source_execution_sha256", None)
    return "sha256:" + hashlib.sha256(
        json.dumps(payload_for_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
