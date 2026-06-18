from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso

from .history_eval import _failing_codes_from_quality_eval, _tier_statuses
from .history_io import quality_loop_history_path
from .policy import BUDGET_CONSUMING_HISTORY_EVENTS
from .utils import _file_sha256, _sha256_jsonable


def append_quality_loop_history(
    cwd: str | Path | None,
    quality_eval: dict[str, Any],
    *,
    verdict: str | None = None,
    plan_path: str | Path | None = None,
    quality_eval_path: str | Path | None = None,
    event_type: str = "quality_eval",
    consumes_budget: bool | None = None,
    execution_path: str | Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append one JSONL quality-loop history entry."""

    path = quality_loop_history_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    if consumes_budget is None:
        consumes_budget = event_type in BUDGET_CONSUMING_HISTORY_EVENTS
    entry = {
        "recorded_at": utc_now_iso(),
        "event_type": event_type,
        "consumes_budget": bool(consumes_budget),
        "session_id": quality_eval.get("session_id"),
        "mode": quality_eval.get("mode"),
        "manuscript_hash": quality_eval.get("manuscript_hash"),
        "quality_eval_path": str(quality_eval_path) if quality_eval_path else None,
        "plan_path": str(plan_path) if plan_path else None,
        "execution_path": str(execution_path) if execution_path else None,
        "quality_eval_sha256": f"sha256:{_file_sha256(quality_eval_path)}" if quality_eval_path else f"sha256:{_sha256_jsonable(quality_eval)}",
        "plan_sha256": f"sha256:{_file_sha256(plan_path)}" if plan_path else None,
        "verdict": verdict,
        "failing_codes": _failing_codes_from_quality_eval(quality_eval),
        "tier_statuses": _tier_statuses(quality_eval),
        "tier_3_overall_score": ((quality_eval.get("tiers") or {}).get("tier_3_scholarly_quality") or {}).get("overall_score") if isinstance(quality_eval.get("tiers"), dict) else None,
        "tier_3_axis_scores": ((quality_eval.get("tiers") or {}).get("tier_3_scholarly_quality") or {}).get("axis_scores") if isinstance(quality_eval.get("tiers"), dict) else {},
    }
    if extra:
        entry.update(extra)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return path
