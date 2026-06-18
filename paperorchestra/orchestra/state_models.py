from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "orchestra-state/1"


@dataclass
class OrchestraFacets:
    session: str = "no_session"
    material: str = "missing"
    source_digest: str = "missing"
    claims: str = "missing"
    evidence: str = "missing"
    citations: str = "not_checked"
    figures: str = "not_checked"
    writing: str = "not_allowed"
    quality: str = "not_evaluated"
    interaction: str = "none"
    omx: str = "not_required"
    artifacts: str = "unknown"

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "OrchestraFacets":
        return cls(**(payload or {}))

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class HardGateStatus:
    status: str = "unknown"
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "HardGateStatus":
        return cls(**(payload or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
        }


@dataclass
class ScoreSummary:
    overall: float = 0.0
    readiness_band: str = "unscored"
    dimensions: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ScoreSummary":
        return cls(**(payload or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "readiness_band": self.readiness_band,
            "dimensions": dict(self.dimensions),
        }


@dataclass
class ReadinessSummary:
    label: str = "needs_material"
    status: str = "blocked"
    rationale: str = "No usable material/session has been inspected yet."

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "ReadinessSummary":
        return cls(**(payload or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "status": self.status,
            "rationale": self.rationale,
        }


@dataclass
class NextAction:
    action_type: str
    reason: str
    requires_omx: bool = False
    omx_surface: str | None = None
    risk: str = "low"
    evidence_required: bool = False
    state_after: Any | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "NextAction":
        data = dict(payload)
        data.pop("state_after", None)
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "reason": self.reason,
            "requires_omx": self.requires_omx,
            "omx_surface": self.omx_surface,
            "risk": self.risk,
            "evidence_required": self.evidence_required,
        }
