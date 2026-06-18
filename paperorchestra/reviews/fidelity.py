from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import load_session
from paperorchestra.reviews.fidelity_checks import build_fidelity_checks
from paperorchestra.reviews.fidelity_types import (
    overall_status as _overall_status,
    status_histogram as _status_histogram,
    summary_descriptor as _summary_descriptor,
)


def run_fidelity_audit(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    checks = build_fidelity_checks(cwd, state)
    histogram = _status_histogram(checks)
    return {
        "session_id": state.session_id,
        "overall_status": _overall_status(checks),
        "status_histogram": histogram,
        "summary_descriptor": _summary_descriptor(checks),
        "checks": [check.to_dict() for check in checks],
    }
