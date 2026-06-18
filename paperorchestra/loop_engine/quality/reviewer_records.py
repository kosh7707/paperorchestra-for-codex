from __future__ import annotations

from typing import Any

from . import review_score as _review_score
from .utils import _file_sha256, _read_json_if_exists


def _reviewer_identity(review: dict[str, Any]) -> str | None:
    provenance = review.get("review_provenance") if isinstance(review, dict) else None
    if not isinstance(provenance, dict):
        return None
    for key in ("reviewer_label", "provider_command_digest", "prompt_trace_meta_sha256", "provider_name"):
        value = provenance.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _current_review_records(state, current_sha: str | None) -> list[dict[str, Any]]:
    paths: list[str] = []
    if state.artifacts.latest_review_json:
        paths.append(state.artifacts.latest_review_json)
    for snapshot in state.review_history:
        if snapshot.raw_path:
            paths.append(snapshot.raw_path)

    records: list[dict[str, Any]] = []
    for raw_path in sorted(dict.fromkeys(paths)):
        payload = _read_json_if_exists(raw_path)
        if not isinstance(payload, dict):
            continue
        if current_sha and payload.get("manuscript_sha256") != current_sha:
            continue
        if _review_score._review_shape_failures(payload, quality_mode="claim_safe"):
            continue
        provenance_failures, _ = _review_score._review_provenance_failures(payload, current_sha=current_sha, quality_mode="claim_safe")
        if provenance_failures:
            continue
        identity = _reviewer_identity(payload)
        if not identity:
            continue
        records.append({"path": raw_path, "sha256": _file_sha256(raw_path), "identity": identity})
    return records
