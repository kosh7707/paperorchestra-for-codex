from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any

from paperorchestra.orchestra.scorecard import build_scorecard_summary
from paperorchestra.orchestra.state_axis_status import derive_five_axis_status
from paperorchestra.orchestra.state_models import (
    SCHEMA_VERSION,
    HardGateStatus,
    NextAction,
    OrchestraFacets,
    ReadinessSummary,
    ScoreSummary,
)
from paperorchestra.orchestra.state_readiness_rules import derive_readiness


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class OrchestraState:
    cwd: str
    schema_version: str = SCHEMA_VERSION
    session_id: str | None = None
    manuscript_sha256: str | None = None
    facets: OrchestraFacets = field(default_factory=OrchestraFacets)
    hard_gates: HardGateStatus = field(default_factory=HardGateStatus)
    scores: ScoreSummary = field(default_factory=ScoreSummary)
    readiness: ReadinessSummary = field(default_factory=ReadinessSummary)
    five_axis_status: dict[str, str] = field(default_factory=dict)
    blocking_reasons: list[str] = field(default_factory=list)
    next_actions: list[NextAction] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    private_safe: bool = True
    private_notes: list[str] = field(default_factory=list, repr=False)
    author_override: str | None = None

    @classmethod
    def new(
        cls,
        *,
        cwd: str | Path,
        facets: OrchestraFacets | None = None,
        hard_gates: HardGateStatus | None = None,
        scores: ScoreSummary | None = None,
        readiness: ReadinessSummary | None = None,
        blocking_reasons: list[str] | None = None,
        next_actions: list[NextAction] | None = None,
        private_notes: list[str] | None = None,
        author_override: str | None = None,
        session_id: str | None = None,
        manuscript_sha256: str | None = None,
    ) -> "OrchestraState":
        state = cls(
            cwd=str(Path(cwd)),
            session_id=session_id,
            manuscript_sha256=manuscript_sha256,
            facets=facets or OrchestraFacets(),
            hard_gates=hard_gates or HardGateStatus(),
            scores=scores or ScoreSummary(),
            readiness=readiness or ReadinessSummary(),
            blocking_reasons=list(blocking_reasons or []),
            next_actions=list(next_actions or []),
            private_notes=list(private_notes or []),
            author_override=author_override,
        )
        state.refresh_derived_fields()
        return state

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OrchestraState":
        state = cls(
            schema_version=payload.get("schema_version", SCHEMA_VERSION),
            cwd=payload["cwd"],
            session_id=payload.get("session_id"),
            manuscript_sha256=payload.get("manuscript_sha256"),
            facets=OrchestraFacets.from_dict(payload.get("facets")),
            hard_gates=HardGateStatus.from_dict(payload.get("hard_gates")),
            scores=ScoreSummary.from_dict(payload.get("scores")),
            readiness=ReadinessSummary.from_dict(payload.get("readiness")),
            five_axis_status=dict(payload.get("five_axis_status", {})),
            blocking_reasons=list(payload.get("blocking_reasons", [])),
            next_actions=[NextAction.from_dict(item) for item in payload.get("next_actions", [])],
            evidence_refs=list(payload.get("evidence_refs", [])),
            private_safe=bool(payload.get("private_safe", True)),
            private_notes=list(payload.get("private_notes", [])),
            author_override=payload.get("author_override"),
        )
        state.refresh_derived_fields(override_readiness=False)
        return state

    def clone(self) -> "OrchestraState":
        return OrchestraState.from_dict(self.to_dict(include_private=True))

    def refresh_derived_fields(self, *, override_readiness: bool = True) -> None:
        if override_readiness:
            self.readiness = derive_readiness(self)
        self.five_axis_status = derive_five_axis_status(self)

    def to_dict(self, *, include_private: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "cwd": self.cwd,
            "session_id": self.session_id,
            "manuscript_sha256": self.manuscript_sha256,
            "facets": self.facets.to_dict(),
            "hard_gates": self.hard_gates.to_dict(),
            "scores": self.scores.to_dict(),
            "scorecard_summary": build_scorecard_summary(self),
            "readiness": self.readiness.to_dict(),
            "five_axis_status": dict(self.five_axis_status),
            "blocking_reasons": list(self.blocking_reasons),
            "next_actions": [action.to_dict() for action in self.next_actions],
            "evidence_refs": list(self.evidence_refs),
            "private_safe": self.private_safe,
            "author_override": self.author_override,
        }
        if include_private:
            payload["private_notes"] = list(self.private_notes)
        return payload

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.to_dict(include_private=False)
        payload["private_safe"] = True
        if payload.get("author_override"):
            payload["author_override"] = "redacted"
        return payload


__all__ = [
    "SCHEMA_VERSION",
    "HardGateStatus",
    "NextAction",
    "OrchestraFacets",
    "OrchestraState",
    "ReadinessSummary",
    "ScoreSummary",
    "derive_five_axis_status",
    "derive_readiness",
    "file_sha256",
]
