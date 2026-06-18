from __future__ import annotations

from dataclasses import dataclass, field

from paperorchestra.orchestra.state import NextAction, OrchestraState

HIGH_CRITICAL_CLAIM_TYPES = {"numeric", "comparative", "security", "novelty", "causal"}
HIGH_CRITICAL_GRAPH_ROLES = {"root", "central_support"}
MEDIUM_CRITICAL_CLAIM_TYPES = {"method", "limitation"}


@dataclass(frozen=True)
class ClaimSignal:
    claim_id: str
    claim_type: str
    graph_role: str
    evidence_status: str = "unknown"
    author_desired_strength: str = "unspecified"


@dataclass(frozen=True)
class EvidenceObligationSignal:
    obligation_id: str
    claim_id: str
    status: str
    machine_solvable: bool = True


@dataclass(frozen=True)
class CitationObligationSignal:
    obligation_id: str
    claim_id: str
    status: str
    critical: bool = False


@dataclass
class DraftControlInput:
    base_state: OrchestraState
    claims: list[ClaimSignal] = field(default_factory=list)
    evidence_obligations: list[EvidenceObligationSignal] = field(default_factory=list)
    citation_obligations: list[CitationObligationSignal] = field(default_factory=list)
    evidence_obligation_map_present: bool = True
    prewriting_notice_acknowledged: bool = False
    author_override: str | None = None


@dataclass
class DraftControlDecision:
    status: str
    state: OrchestraState
    actions: list[NextAction]
    reasons: list[str] = field(default_factory=list)
    draft_allowed: bool = False
