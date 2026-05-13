from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .orchestra_scorecard import build_scorecard_summary

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
    state_after: "OrchestraState | None" = None

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


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derive_readiness(state: OrchestraState) -> ReadinessSummary:
    facets = state.facets
    if state.hard_gates.status == "fail":
        return ReadinessSummary("not_ready", "blocked", "Hard gate failures block readiness.")
    if state.author_override and (facets.claims == "conflict" or facets.evidence in {"unresolved", "blocked"}):
        return ReadinessSummary("not_ready", "blocked", "Author override conflicts with current evidence.")
    if facets.omx == "required_missing":
        return ReadinessSummary("not_ready", "blocked", "Strict OMX evidence is required but missing.")
    if facets.figures in {"placeholder_only", "inventory_needed", "blocked"} and facets.quality in {
        "near_ready",
        "human_finalization_candidate",
    }:
        return ReadinessSummary("not_ready", "blocked", "Figure gate prevents final readiness.")
    if facets.session == "no_session" and facets.material == "missing":
        return ReadinessSummary("needs_material", "blocked", "No session or material has been provided.")
    if facets.material == "inventory_needed":
        return ReadinessSummary("intake_needed", "blocked", "Material must be inventoried before drafting.")
    if facets.evidence in {"research_needed", "durable_research_needed"}:
        return ReadinessSummary("research_needed", "blocked", "Machine-solvable evidence work remains.")
    if facets.claims == "conflict" or facets.interaction == "human_needed":
        return ReadinessSummary("human_needed", "blocked", "Author judgment is required.")
    if facets.quality == "repairable":
        return ReadinessSummary("repair_needed", "blocked", "Repair loop is required.")
    if facets.quality == "hard_gate_failed":
        return ReadinessSummary("not_ready", "blocked", "Quality hard gate failed.")
    if facets.quality == "human_finalization_candidate" and state.hard_gates.status in {"pass", "unknown"}:
        return ReadinessSummary("ready_for_human_finalization", "ready", "Automation is ready for human finalization.")
    if (
        facets.material == "inventoried_sufficient"
        and facets.source_digest == "ready"
        and facets.claims == "validated"
        and facets.evidence == "supported"
        and facets.writing == "not_allowed"
    ):
        return ReadinessSummary("draft_blocked", "blocked", "Prewriting notice must be shown before drafting.")
    if facets.writing == "drafting_allowed":
        return ReadinessSummary("ready_for_drafting", "ready", "Drafting is allowed by current state.")
    if facets.session in {"draft_available", "compiled"}:
        return ReadinessSummary("not_ready", "blocked", "Draft exists but claim-safe quality readiness is not established.")
    return ReadinessSummary("not_ready", "blocked", "State is not ready.")


def derive_five_axis_status(state: OrchestraState) -> dict[str, str]:
    facets = state.facets
    materials = {
        "missing": "missing",
        "inventory_needed": "insufficient",
        "inventoried_insufficient": "insufficient",
        "inventoried_sufficient": "ready",
        "blocked": "blocked",
    }.get(facets.material, "missing")
    if facets.source_digest == "ready" and materials == "ready":
        materials = "ready"

    claims = "missing"
    if facets.claims == "conflict":
        claims = "conflict"
    elif facets.evidence in {"research_needed", "durable_research_needed"}:
        claims = "needs_research"
    elif facets.claims == "validated" and facets.evidence == "supported":
        claims = "supported"
    elif facets.claims == "blocked" or facets.evidence == "blocked":
        claims = "blocked"

    citations = {
        "not_checked": "not_checked",
        "unknown_refs": "unknown_refs",
        "unsupported_critical": "unsupported",
        "warnings_only": "warnings",
        "supported": "supported",
    }.get(facets.citations, "not_checked")

    figures = {
        "not_checked": "not_checked",
        "inventory_needed": "needs_inventory",
        "placeholder_only": "placeholder",
        "matched": "matched",
        "human_finalization_needed": "human_polish",
        "blocked": "blocked",
    }.get(facets.figures, "not_checked")

    readiness = state.readiness.label
    return {
        "materials": materials,
        "claims": claims,
        "citations": citations,
        "figures": figures,
        "readiness": readiness,
    }
