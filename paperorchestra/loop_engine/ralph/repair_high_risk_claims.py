from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.loop_engine.ralph.repair_claim_safety_artifacts import _quality_eval_artifact
from paperorchestra.loop_engine.ralph.repair_issue_text import _truncate_issue_text


def _high_risk_repair_issues(cwd: str | Path | None, *, limit: int = 16) -> list[dict[str, Any]]:
    sweep = _high_risk_claim_sweep(cwd)
    issues: list[dict[str, Any]] = []
    for item in sweep.get("items") or []:
        if not isinstance(item, dict):
            continue
        issues.append(
            {
                "issue_type": "high_risk_uncited_claim",
                "line": item.get("line"),
                "sentence": _truncate_issue_text(item.get("sentence")),
                "reason": _truncate_issue_text(item.get("reason"), limit=500),
                "required_action": "ground with existing verified evidence, scope as a limitation/author-material claim, or delete",
            }
        )
        if len(issues) >= limit:
            break
    return issues


def _high_risk_claim_sweep(cwd: str | Path | None) -> dict[str, Any]:
    quality_eval = _quality_eval_artifact(cwd)
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else {}
    return sweep
