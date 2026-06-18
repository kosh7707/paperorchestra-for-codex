from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReproducibilityReasons:
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.blocking:
            return "BLOCK"
        if self.warnings:
            return "WARN"
        return "OK"

    @property
    def combined(self) -> list[str]:
        return [*self.blocking, *self.warnings]
