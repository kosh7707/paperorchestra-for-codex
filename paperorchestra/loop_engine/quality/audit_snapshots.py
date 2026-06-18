from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.reviews.fidelity import run_fidelity_audit
from paperorchestra.reviews.reproducibility import build_reproducibility_audit, write_reproducibility_audit


def build_quality_audits(
    cwd: str | Path | None,
    *,
    require_live_verification: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build current reproducibility and fidelity audit payloads without writing session state."""

    reproducibility_payload = build_reproducibility_audit(
        cwd,
        require_live_verification=require_live_verification,
    )
    fidelity_payload = run_fidelity_audit(cwd)
    return reproducibility_payload, fidelity_payload


def refresh_quality_audit_artifacts(
    cwd: str | Path | None,
    *,
    require_live_verification: bool,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Refresh audit artifacts needed by quality-eval and QA-loop planning."""

    fidelity_payload = run_fidelity_audit(cwd)
    fidelity_path = artifact_path(cwd, "fidelity.audit.json")
    write_json(fidelity_path, fidelity_payload)

    state = load_session(cwd)
    state.artifacts.latest_fidelity_json = str(fidelity_path)
    save_session(cwd, state)

    write_reproducibility_audit(cwd, require_live_verification=require_live_verification)
    reproducibility_payload = build_reproducibility_audit(
        cwd,
        require_live_verification=require_live_verification,
    )
    return state, reproducibility_payload, fidelity_payload
