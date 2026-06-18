from __future__ import annotations

from paperorchestra.orchestra.consensus import CriticConsensus
from paperorchestra.orchestra.scoring import ScholarlyScore, ScoringInputBundle
from paperorchestra.orchestra.state import OrchestraState
from paperorchestra.orchestra.verifier_consensus_items import (
    ACCEPTED_CONSENSUS_BANDS,
    _consensus_count_item,
    _consensus_readiness_item,
)
from paperorchestra.orchestra.verifier_item_helpers import _item, _safe_ref
from paperorchestra.orchestra.verifier_records import VerifierChecklistItem
from paperorchestra.orchestra.verifier_scoring_items import SHA256_RE as _SHA256_RE
from paperorchestra.orchestra.verifier_scoring_items import _score_item, _scoring_bundle_item


def _hard_gate_item(state: OrchestraState) -> VerifierChecklistItem:
    if state.hard_gates.status == "pass":
        return _item("hard_gates_no_fail", "pass", "hard_gates_pass")
    if state.hard_gates.status == "fail":
        return _item("hard_gates_no_fail", "fail", "hard_gate_failure")
    return _item("hard_gates_no_fail", "blocked", "hard_gates_not_evaluated")


def _compile_export_item(*, compiled: bool, exported: bool, unsafe: bool) -> VerifierChecklistItem:
    if unsafe:
        return _item("compile_export_accounted_for", "fail", "compile_export_artifact_refs_unsafe")
    if compiled and exported:
        return _item("compile_export_accounted_for", "pass", "compile_and_export_accounted_for")
    return _item("compile_export_accounted_for", "blocked", "compile_or_export_not_accounted_for")


def _public_safety_item(unsafe_reasons: list[str]) -> VerifierChecklistItem:
    if unsafe_reasons:
        return _item("public_safety_no_raw_private_evidence", "fail", "unsafe_public_evidence_detected")
    return _item("public_safety_no_raw_private_evidence", "pass", "public_safety_checks_pass")


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
