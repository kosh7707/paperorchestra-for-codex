from __future__ import annotations

from typing import Any

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _profile(name: str, description: str, ready: bool, missing: list[str], next_steps: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "ready": ready,
        "status": "ok" if ready else "warning",
        "missing": missing,
        "next_steps": next_steps,
    }
