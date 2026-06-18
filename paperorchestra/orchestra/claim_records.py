from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ClaimCandidate:
    claim_id: str
    claim_type: str
    graph_role: str
    criticality: str
    text_sha256: str
    text_label: str
    source_label: str
    source_sha256: str
    raw_text: str | None = field(default=None, repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "graph_role": self.graph_role,
            "criticality": self.criticality,
            "text_sha256": self.text_sha256,
            "text_label": self.text_label,
            "source_label": self.source_label,
            "source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class EvidenceObligation:
    obligation_id: str
    claim_id: str
    status: str
    criticality: str
    machine_solvable: bool = True
    reason: str = "claim_requires_source_support"

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class CitationObligation:
    obligation_id: str
    claim_id: str
    status: str
    critical: bool
    machine_solvable: bool = True
    reason: str = "claim_requires_citation_support"

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ClaimGraphReport:
    schema_version: str
    status: str
    ready: bool
    claim_count: int
    claims: list[ClaimCandidate] = field(default_factory=list)
    evidence_obligations: list[EvidenceObligation] = field(default_factory=list)
    citation_obligations: list[CitationObligation] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "ready": self.ready,
            "claim_count": self.claim_count,
            "claims": [claim.to_public_dict() for claim in self.claims],
            "evidence_obligations": [item.to_public_dict() for item in self.evidence_obligations],
            "citation_obligations": [item.to_public_dict() for item in self.citation_obligations],
            "blocking_reasons": list(self.blocking_reasons),
            "private_safe_summary": self.private_safe_summary,
        }


@dataclass(frozen=True)
class SourceText:
    path: Path
    path_sha256: str
    source_label: str
    text: str
