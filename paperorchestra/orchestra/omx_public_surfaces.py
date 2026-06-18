from __future__ import annotations

ALLOWED_SKILL_SURFACES = {
    "$autoresearch",
    "$autoresearch-goal",
    "$deep-interview",
    "$ralplan",
    "$ralph",
    "$ultraqa",
    "$trace",
}


def _validate_skill_surface(surface: str) -> None:
    if surface not in ALLOWED_SKILL_SURFACES:
        raise ValueError(f"Unsupported planned OMX skill surface: {surface!r}")
