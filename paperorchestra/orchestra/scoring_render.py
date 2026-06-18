from __future__ import annotations

from paperorchestra.orchestra.scholarly_score import ScholarlyScore


def render_compact_scorecard(score: ScholarlyScore, *, blockers: list[str] | None = None) -> str:
    summary = score.to_summary()
    blockers = list(blockers or summary["blocking_reasons"])
    lines = [
        f"Paper readiness score: {score.overall:.0f}/100 — {score.readiness_band}",
        "",
        "Weakest dimensions:",
    ]
    weakest = summary["weakest_dimensions"]
    if weakest:
        for item in weakest:
            lines.append(f"- {item['dimension']}: {item['score']:.0f}")
    else:
        lines.append("- unavailable: full scorecard dimensions missing")
    lines.extend(["", "Current blockers:"])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none recorded")
    lines.extend(
        [
            "",
            "Next:",
            "- Use the weakest dimensions and blockers to prioritize repair.",
            "- Hard gates still override this scorecard.",
        ]
    )
    return "\n".join(lines)
