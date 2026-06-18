from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.ralph.commands import MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME
from paperorchestra.loop_engine.ralph.io_files import _artifact_sha, _text_sha256, atomic_write_text


def _candidate_write_marker_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, MANUSCRIPT_CANDIDATE_WRITE_MARKER_FILENAME)


def clear_pending_manuscript_write(cwd: str | Path | None, *, status: str = "resolved", reason: str | None = None) -> None:
    marker_path = _candidate_write_marker_path(cwd)
    if not marker_path.exists():
        return
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if isinstance(marker, dict):
            marker["status"] = status
            marker["resolved_at"] = utc_now_iso()
            if reason:
                marker["resolution_reason"] = reason
            atomic_write_text(marker_path, json.dumps(marker, indent=2, sort_keys=True) + "\n")
    finally:
        marker_path.unlink(missing_ok=True)


def guarded_replace_manuscript_text(
    cwd: str | Path | None,
    manuscript_path: str | Path,
    replacement_text: str,
    *,
    reason: str,
    original_text: str | None = None,
) -> Path:
    destination = Path(manuscript_path)
    if original_text is None:
        original_text = destination.read_text(encoding="utf-8") if destination.exists() else ""
    marker_path = _candidate_write_marker_path(cwd)
    snapshot_name = f"paper.full.tex.pre-candidate-{uuid.uuid4().hex[:12]}.tex"
    snapshot_path = artifact_path(cwd, snapshot_name)
    atomic_write_text(snapshot_path, original_text)
    marker = {
        "schema_version": "ralph-candidate-write/1",
        "status": "pending",
        "created_at": utc_now_iso(),
        "reason": reason,
        "destination_path": str(destination),
        "original_snapshot_path": str(snapshot_path),
        "original_sha256": _text_sha256(original_text),
        "candidate_sha256": _text_sha256(replacement_text),
    }
    atomic_write_text(marker_path, json.dumps(marker, indent=2, sort_keys=True) + "\n")
    atomic_write_text(destination, replacement_text)
    return marker_path


def recover_pending_manuscript_write(cwd: str | Path | None) -> dict[str, Any]:
    try:
        marker_path = _candidate_write_marker_path(cwd)
    except FileNotFoundError:
        return {"status": "none", "reason": "no_current_session"}
    if not marker_path.exists():
        return {"status": "none"}
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "blocked", "marker_path": str(marker_path), "reason": f"invalid_marker_json: {exc}"}
    if not isinstance(marker, dict):
        return {"status": "blocked", "marker_path": str(marker_path), "reason": "invalid_marker"}
    destination = Path(str(marker.get("destination_path") or ""))
    snapshot_path = Path(str(marker.get("original_snapshot_path") or ""))
    original_sha = str(marker.get("original_sha256") or "")
    candidate_sha = str(marker.get("candidate_sha256") or "")
    current_sha = _artifact_sha(destination)
    if current_sha == original_sha:
        clear_pending_manuscript_write(cwd, status="resolved", reason="destination_already_original")
        return {"status": "already_original", "marker_path": str(marker_path), "destination_sha256": current_sha}
    if snapshot_path.exists():
        original_text = snapshot_path.read_text(encoding="utf-8")
        if _text_sha256(original_text) != original_sha:
            return {"status": "blocked", "marker_path": str(marker_path), "reason": "original_snapshot_sha_mismatch"}
        atomic_write_text(destination, original_text)
        clear_pending_manuscript_write(cwd, status="restored", reason="pending_candidate_recovered")
        return {
            "status": "restored_original",
            "marker_path": str(marker_path),
            "destination_path": str(destination),
            "previous_destination_sha256": current_sha,
            "candidate_sha256": candidate_sha,
            "original_sha256": original_sha,
        }
    return {"status": "blocked", "marker_path": str(marker_path), "reason": "original_snapshot_missing"}
