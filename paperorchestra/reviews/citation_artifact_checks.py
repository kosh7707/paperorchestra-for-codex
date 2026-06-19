from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.quality.utils import _file_sha256, _read_json_if_exists


_FAILING_STATUSES = {"fail", "failed", "reject", "rejected", "block", "blocked"}
_PASSING_CRITIC_STATUSES = {"pass", "ok", "warn", "warning"}


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
    failing = _binding_failures(
        payload,
        expected_manuscript_sha256=expected_manuscript_sha256,
        stale_code=stale_code,
        unbound_code=unbound_code or stale_code,
        require_binding=require_binding,
    )
    status = _payload_status(payload)
    if status in _FAILING_STATUSES:
        failing.append(failed_code)
    _extend_payload_failing_codes(failing, payload)
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
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

    failing = _binding_failures(
        payload,
        expected_manuscript_sha256=expected_manuscript_sha256,
        stale_code=f"{name}_stale",
        unbound_code=f"{name}_unbound",
        require_binding=require_binding,
    )
    artifact_status = _payload_status(payload)
    if artifact_status not in _PASSING_CRITIC_STATUSES:
        failing.append(f"{name}_{artifact_status or 'unknown'}")
    _extend_payload_failing_codes(failing, payload)
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
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


def _binding_failures(
    payload: dict[str, Any],
    *,
    expected_manuscript_sha256: str | None,
    stale_code: str,
    unbound_code: str,
    require_binding: bool,
) -> list[str]:
    manuscript_sha = payload.get("manuscript_sha256") or payload.get("paper_full_tex_sha256")
    failing: list[str] = []
    if require_binding and expected_manuscript_sha256 and not manuscript_sha:
        failing.append(unbound_code)
    if expected_manuscript_sha256 and manuscript_sha and manuscript_sha != expected_manuscript_sha256:
        failing.append(stale_code)
    return failing


def _extend_payload_failing_codes(failing: list[str], payload: dict[str, Any]) -> None:
    failing.extend(code for code in payload.get("failing_codes") or [] if isinstance(code, str) and code)


__all__ = ["_artifact_check", "_critic_review_artifact", "_payload_status"]
