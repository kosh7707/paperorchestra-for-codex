from __future__ import annotations

from paperorchestra.orchestra.draft_control_criticality import claim_signal_criticality
from paperorchestra.orchestra.draft_control_evaluation import DraftControlEvaluation
from paperorchestra.orchestra.draft_control_models import (
    HIGH_CRITICAL_CLAIM_TYPES,
    HIGH_CRITICAL_GRAPH_ROLES,
    MEDIUM_CRITICAL_CLAIM_TYPES,
    CitationObligationSignal,
    ClaimSignal,
    DraftControlDecision,
    DraftControlInput,
    EvidenceObligationSignal,
)


class DraftControlPolicy:
    def evaluate(self, inputs: DraftControlInput) -> DraftControlDecision:
        return DraftControlEvaluation(inputs).run()

__all__ = [
    "CitationObligationSignal",
    "ClaimSignal",
    "DraftControlDecision",
    "DraftControlInput",
    "DraftControlPolicy",
    "EvidenceObligationSignal",
    "HIGH_CRITICAL_CLAIM_TYPES",
    "HIGH_CRITICAL_GRAPH_ROLES",
    "MEDIUM_CRITICAL_CLAIM_TYPES",
    "claim_signal_criticality",
]
