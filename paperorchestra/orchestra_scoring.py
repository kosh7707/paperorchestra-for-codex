from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScoringInputBundle:
    schema_version: str
    phase: str
    manuscript_sha256: str
    required_artifacts: dict[str, str]
    compressed_evidence: dict[str, Any]
    complete: bool
    blocking_reasons: list[str] = field(default_factory=list)
    private_raw_text: str | None = field(default=None, repr=False)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "phase": self.phase,
            "manuscript_sha256": self.manuscript_sha256,
            "required_artifacts": dict(self.required_artifacts),
            "compressed_evidence": dict(self.compressed_evidence),
            "complete": self.complete,
            "blocking_reasons": list(self.blocking_reasons),
            "private_safe": True,
        }


class ScoringBundleBuilder:
    def build(
        self,
        *,
        phase: str,
        manuscript_sha256: str,
        required_artifacts: dict[str, str],
        compressed_evidence: dict[str, Any],
        private_raw_text: str | None = None,
    ) -> ScoringInputBundle:
        blockers: list[str] = []
        if len(manuscript_sha256) != 64:
            blockers.append("invalid_manuscript_sha256")
        for name, ref in required_artifacts.items():
            if not ref:
                blockers.append(f"missing_required_artifact:{name}")
        return ScoringInputBundle(
            schema_version="scholarly-score-input-bundle/1",
            phase=phase,
            manuscript_sha256=manuscript_sha256,
            required_artifacts=dict(required_artifacts),
            compressed_evidence=dict(compressed_evidence),
            complete=not blockers,
            blocking_reasons=blockers,
            private_raw_text=private_raw_text,
        )


@dataclass
class ScholarlyScore:
    overall: float
    readiness_band: str
    evidence_links: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.evidence_links and "missing_evidence_links" not in self.blocking_reasons:
            self.blocking_reasons.append("missing_evidence_links")

    @property
    def valid(self) -> bool:
        return not self.blocking_reasons
