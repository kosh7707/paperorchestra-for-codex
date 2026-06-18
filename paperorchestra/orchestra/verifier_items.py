from __future__ import annotations

from paperorchestra.orchestra.consensus import CriticConsensus
from paperorchestra.orchestra.scoring import ScholarlyScore, ScoringInputBundle
from paperorchestra.orchestra.state import OrchestraState
from paperorchestra.orchestra.verifier_consensus_items import (
    ACCEPTED_CONSENSUS_BANDS,
    _consensus_count_item,
    _consensus_readiness_item,
)
from paperorchestra.orchestra.verifier_execution_items import _compile_export_item, _hard_gate_item, _public_safety_item
from paperorchestra.orchestra.verifier_item_helpers import _item, _safe_ref
from paperorchestra.orchestra.verifier_records import VerifierChecklistItem
from paperorchestra.orchestra.verifier_scoring_items import SHA256_RE as _SHA256_RE
from paperorchestra.orchestra.verifier_scoring_items import _score_item, _scoring_bundle_item


def build_verifier_items(
    state: OrchestraState,
    scoring_bundle: ScoringInputBundle | None,
    score: ScholarlyScore | None,
    consensus: CriticConsensus | None,
    *,
    compiled: bool,
    exported: bool,
    unsafe_reasons: list[str],
) -> list[VerifierChecklistItem]:
    return [
        _scoring_bundle_item(scoring_bundle),
        _score_item(score),
        _consensus_count_item(consensus),
        _consensus_readiness_item(consensus),
        _hard_gate_item(state),
        _compile_export_item(compiled=compiled, exported=exported, unsafe=bool(unsafe_reasons)),
        _public_safety_item(unsafe_reasons),
    ]


__all__ = [
    "ACCEPTED_CONSENSUS_BANDS",
    "_SHA256_RE",
    "_compile_export_item",
    "_consensus_count_item",
    "_consensus_readiness_item",
    "_hard_gate_item",
    "_item",
    "_public_safety_item",
    "_safe_ref",
    "_score_item",
    "_scoring_bundle_item",
    "build_verifier_items",
]
