from __future__ import annotations

from pathlib import Path
from typing import Any

from .quality_loop_utils import _file_sha256, _read_json_if_exists
from .session import artifact_path

CITATION_INTEGRITY_AUDIT_FILENAME = "citation_integrity.audit.json"
CITATION_INTEGRITY_CRITIC_FILENAME = "citation_integrity.critic.json"
RENDERED_REFERENCE_AUDIT_FILENAME = "rendered_reference_audit.json"


def citation_integrity_audit_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTEGRITY_AUDIT_FILENAME)


def citation_integrity_critic_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, CITATION_INTEGRITY_CRITIC_FILENAME)


def rendered_reference_audit_path(cwd: str | Path | None) -> Path:
    return artifact_path(cwd, RENDERED_REFERENCE_AUDIT_FILENAME)


def _payload_status(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("status") or payload.get("verdict") or payload.get("overall_status")
    return str(raw).strip().lower() if raw is not None else None


def _artifact_check(path: Path, *, expected_manuscript_sha256: str | None, missing_code: str, stale_code: str, failed_code: str, unbound_code: str | None = None, require_binding: bool = False) -> dict[str, Any]:
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
    return {
        "status": "fail" if failing else "pass",
        "path": str(path),
        "sha256": _file_sha256(path),
        "artifact_status": status,
        "manuscript_sha256": manuscript_sha,
        "expected_manuscript_sha256": expected_manuscript_sha256,
        "failing_codes": sorted(dict.fromkeys(failing)),
    }


def citation_integrity_check(cwd: str | Path | None, state: Any, *, quality_mode: str = "ralph") -> dict[str, Any]:
    """Return the claim-safe Citation Integrity/Critic gate status.

    Batch A intentionally establishes the gate contract and fail-closed behavior.
    Batch B fills in the rendered-reference and claim/source support internals.
    """

    expected_manuscript_sha256 = _file_sha256(state.artifacts.paper_full_tex)
    integrity_path = citation_integrity_audit_path(cwd)
    critic_path = citation_integrity_critic_path(cwd)
    rendered_path = rendered_reference_audit_path(cwd)
    integrity = _artifact_check(
        integrity_path,
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="citation_integrity_missing",
        stale_code="citation_integrity_stale",
        failed_code="citation_integrity_failed",
        unbound_code="citation_integrity_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    critic = _artifact_check(
        critic_path,
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="citation_critic_missing",
        stale_code="citation_critic_stale",
        failed_code="citation_critic_failed",
        unbound_code="citation_critic_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    rendered = _artifact_check(
        rendered_path,
        expected_manuscript_sha256=expected_manuscript_sha256,
        missing_code="rendered_reference_audit_missing",
        stale_code="rendered_reference_audit_stale",
        failed_code="rendered_reference_audit_failed",
        unbound_code="rendered_reference_audit_unbound",
        require_binding=quality_mode == "claim_safe",
    )
    failing_codes: list[str] = []
    if quality_mode == "claim_safe":
        failing_codes.extend(integrity["failing_codes"])
        failing_codes.extend(critic["failing_codes"])
        failing_codes.extend(rendered["failing_codes"])
    else:
        for check in (integrity, critic, rendered):
            failing_codes.extend(code for code in check["failing_codes"] if not code.endswith("_missing"))
    return {
        "status": "fail" if failing_codes else "pass",
        "failing_codes": sorted(dict.fromkeys(failing_codes)),
        "manuscript_sha256": expected_manuscript_sha256,
        "citation_integrity_audit": integrity,
        "citation_integrity_critic": critic,
        "rendered_reference_audit": rendered,
        "mode_effect": "hard_fail_in_claim_safe" if quality_mode == "claim_safe" else "missing_artifacts_allowed_outside_claim_safe",
    }
