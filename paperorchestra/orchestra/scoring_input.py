from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from paperorchestra.orchestra.scoring_public import _public_blocking_reason


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
            "blocking_reasons": [_public_blocking_reason(reason) for reason in self.blocking_reasons],
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
