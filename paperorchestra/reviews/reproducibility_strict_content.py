from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from paperorchestra.reviews.reproducibility_strict_figures import (
    STRICT_FIGURE_WARNING_CODES,
    _strict_figure_payload_issues,
    _strict_figure_review_issues,
)
from paperorchestra.reviews.reproducibility_strict_validation import (
    STRICT_VALIDATION_WARNING_CODES,
    _strict_validation_report_issues,
    _strict_validation_warning_issues,
)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _strict_content_gates_enabled() -> bool:
    return _env_flag("PAPERO_STRICT_CONTENT_GATES")


def _strict_content_gate_issues(state, session_artifact_dir: Path | None) -> list[dict[str, Any]]:
    issues = _strict_validation_report_issues(state, session_artifact_dir)
    issues.extend(_strict_figure_review_issues(state, session_artifact_dir))
    return issues
