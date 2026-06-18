from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path
from paperorchestra.loop_engine.ralph.repair_recheck_metrics import _high_risk_metrics
from paperorchestra.loop_engine.ralph.state import _read_json


def _canonical_high_risk_baseline(
    cwd: str | Path | None,
    *,
    original_manuscript_hash: str | None,
) -> tuple[dict[str, Any] | None, str]:
    quality_path = artifact_path(cwd, "quality-eval.json")
    try:
        quality_eval = _read_json(quality_path)
    except Exception:
        return None, "quality_eval_missing"
    if not isinstance(quality_eval, dict):
        return None, "quality_eval_missing"
    expected_hash = str(original_manuscript_hash or "").strip()
    if expected_hash and not expected_hash.startswith("sha256:"):
        expected_hash = "sha256:" + expected_hash
    recorded_hash = str(quality_eval.get("manuscript_hash") or "").strip()
    if expected_hash and recorded_hash and recorded_hash != expected_hash:
        return None, "quality_eval_stale_ignored"
    if expected_hash and not recorded_hash:
        return None, "quality_eval_unbound_ignored"
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    sweep = checks.get("high_risk_claim_sweep") if isinstance(checks.get("high_risk_claim_sweep"), dict) else None
    if not isinstance(sweep, dict):
        return None, "quality_eval_high_risk_missing"
    return _high_risk_metrics(sweep), "quality_eval"
