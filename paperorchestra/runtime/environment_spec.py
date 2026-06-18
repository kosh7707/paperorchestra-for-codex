from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EnvironmentVariableSpec:
    name: str
    category: str
    operator_settable: bool
    default: str | None
    example: str | None
    description: str
    required_for: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["EnvironmentVariableSpec"]
