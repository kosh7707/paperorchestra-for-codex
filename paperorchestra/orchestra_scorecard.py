from __future__ import annotations

from typing import Any

from .orchestra_scoring import SCORE_DIMENSIONS


def build_scorecard_summary(state: Any) -> dict[str, Any]:
    scores = state.scores
    hard_gates = state.hard_gates
    readiness = state.readiness
    accepted_dimensions = {
        dimension: float(value)
        for dimension, value in getattr(scores, "dimensions", {}).items()
        if dimension in SCORE_DIMENSIONS and _is_number(value)
    }
    blockers = list(getattr(state, "blocking_reasons", []))
    if hard_gates.status == "fail":
        blockers = list(dict.fromkeys([*hard_gates.failures, *blockers]))
    status = _score_status(scores, hard_gates)
    weakest = sorted(
        ({"dimension": dimension, "score": value} for dimension, value in accepted_dimensions.items()),
        key=lambda item: item["score"],
    )[:3]
    return {
        "schema_version": "orchestra-scorecard-summary/1",
        "status": status,
        "overall": float(scores.overall) if _is_number(scores.overall) else 0.0,
        "readiness_band": scores.readiness_band,
        "weakest_dimensions": weakest,
        "blockers": [_public_blocker(blocker) for blocker in blockers],
        "readiness_label": readiness.label,
        "readiness_status": readiness.status,
        "private_safe": True,
    }


def render_scorecard_summary(summary: dict[str, Any]) -> str:
    if summary.get("status") == "unscored":
        return "Score: unscored"
    lines = [f"Score: {float(summary.get('overall', 0.0)):.0f}/100 — {summary.get('readiness_band', 'unscored')}"]
    weakest = summary.get("weakest_dimensions")
    if isinstance(weakest, list) and weakest:
        lines.append(
            "Weakest: "
            + ", ".join(
                f"{item.get('dimension')}: {float(item.get('score', 0.0)):.0f}"
                for item in weakest
                if isinstance(item, dict)
            )
        )
    blockers = summary.get("blockers")
    if isinstance(blockers, list) and blockers:
        lines.append("Blockers: " + "; ".join(str(blocker) for blocker in blockers[:3]))
    return "\n".join(lines)


def _score_status(scores: Any, hard_gates: Any) -> str:
    if hard_gates.status == "fail":
        return "blocked_by_hard_gate"
    if scores.readiness_band == "unscored" and not scores.dimensions and not scores.overall:
        return "unscored"
    return "scored"


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _public_blocker(blocker: str) -> str:
    if str(blocker).startswith("unknown_score_dimension:"):
        return "unknown_score_dimension:<redacted>"
    return str(blocker)
