from __future__ import annotations

from typing import Any


def _semantic_metric_count(metrics: dict[str, Any], key: str) -> int | None:
    value = metrics.get(key) if isinstance(metrics, dict) else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _semantic_recheck_gate_summary(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(payload, dict):
        return None, []
    summary: dict[str, Any] = {"status": str(payload.get("status") or "unknown")}
    blockers: list[str] = []
    for lane_name, count_key, blocker in (
        ("citation_integrity", "target_issue_count", "citation_integrity_not_improved"),
        ("high_risk_claim_sweep", "item_count", "high_risk_claim_sweep_not_improved"),
    ):
        lane = _compact_semantic_lane(payload.get(lane_name), count_key=count_key, blocker=blocker, blockers=blockers)
        if lane is not None:
            summary[lane_name] = lane
    return summary, sorted(dict.fromkeys(blockers))


def _compact_semantic_lane(
    lane: Any,
    *,
    count_key: str,
    blocker: str,
    blockers: list[str],
) -> dict[str, Any] | None:
    if not isinstance(lane, dict):
        return None
    before = lane.get("before") if isinstance(lane.get("before"), dict) else {}
    after = lane.get("after") if isinstance(lane.get("after"), dict) else {}
    targeted = bool(lane.get("targeted"))
    improved = bool(lane.get("improved"))
    if targeted and not improved:
        blockers.append(blocker)
    compact: dict[str, Any] = {
        "targeted": targeted,
        "improved": improved,
        "before_count": _semantic_metric_count(before, count_key),
        "after_count": _semantic_metric_count(after, count_key),
    }
    for key in ("baseline_source", "path", "sha256"):
        if lane.get(key):
            compact[key] = lane.get(key)
    return compact
