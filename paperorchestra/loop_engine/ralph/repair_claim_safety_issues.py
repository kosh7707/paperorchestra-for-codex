from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.repair_citation_density import _citation_density_repair_issues
from paperorchestra.loop_engine.ralph.repair_duplicate_support import _duplicate_support_repair_issues
from paperorchestra.loop_engine.ralph.repair_high_risk_claims import _high_risk_repair_issues
from paperorchestra.loop_engine.ralph.repair_issue_text import _truncate_issue_text


def _claim_safety_repair_issues(cwd: str | Path | None) -> list[dict[str, Any]]:
    return _citation_density_repair_issues(cwd) + _duplicate_support_repair_issues(cwd) + _high_risk_repair_issues(cwd)


__all__ = [
    "_claim_safety_repair_issues",
    "_citation_density_repair_issues",
    "_duplicate_support_repair_issues",
    "_high_risk_repair_issues",
    "_truncate_issue_text",
]
