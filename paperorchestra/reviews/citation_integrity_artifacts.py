from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


def _payload_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("status") or payload.get("verdict") or payload.get("overall_status")
    return str(raw).strip().lower() if raw is not None else None


def _artifact_check(
    path: Path,
    *,
    expected_manuscript_sha256: str | None,
    missing_code: str,
    stale_code: str,
    failed_code: str,
    unbound_code: str | None = None,
    require_binding: bool = False,
) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "status": "fail",
            "path": str(path),
            "sha256": None,
            "failing_codes": [missing_code],
            "reason": "missing_or_unreadable",
        }
    failing: list[str] = []
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
    if require_binding and expected_manuscript_sha256 and not manuscript_sha:
        failing.append(unbound_code or stale_code)
    if expected_manuscript_sha256 and manuscript_sha and manuscript_sha != expected_manuscript_sha256:
        failing.append(stale_code)
    status = _payload_status(payload)
    if status in {"fail", "failed", "reject", "rejected", "block", "blocked"}:
        failing.append(failed_code)
    for code in payload.get("failing_codes") or []:
        if isinstance(code, str) and code:
            failing.append(code)
    return {
        "status": "fail" if failing else "pass",
        "path": str(path),
        "sha256": _file_sha256(path),
        "artifact_status": status,
        "manuscript_sha256": manuscript_sha,
        "expected_manuscript_sha256": expected_manuscript_sha256,
        "failing_codes": sorted(dict.fromkeys(failing)),
    }


def _critic_review_artifact(
    name: str,
    path: Path,
    *,
    expected_manuscript_sha256: str | None,
    require_binding: bool,
) -> dict[str, Any]:
    payload = _read_json_if_exists(path)
    if not isinstance(payload, dict):
        return {
            "name": name,
            "path": str(path),
            "sha256": None,
            "artifact_status": None,
            "manuscript_sha256": None,
            "status": "fail",
            "failing_codes": [f"{name}_missing"],
            "reason": "missing_or_unreadable",
        }

    failing: list[str] = []
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
    if require_binding and expected_manuscript_sha256 and not manuscript_sha:
        failing.append(f"{name}_unbound")
    if expected_manuscript_sha256 and manuscript_sha and manuscript_sha != expected_manuscript_sha256:
        failing.append(f"{name}_stale")

    artifact_status = _payload_status(payload)
    if artifact_status not in {"pass", "ok", "warn", "warning"}:
        failing.append(f"{name}_{artifact_status or 'unknown'}")
    for code in payload.get("failing_codes") or []:
        if isinstance(code, str) and code:
            failing.append(code)

    return {
        "name": name,
        "path": str(path),
        "sha256": _file_sha256(path),
        "artifact_status": artifact_status,
        "manuscript_sha256": manuscript_sha,
        "expected_manuscript_sha256": expected_manuscript_sha256,
        "status": "fail" if failing else "pass",
        "failing_codes": sorted(dict.fromkeys(failing)),
    }
