from __future__ import annotations

from paperorchestra.orchestra.consensus import CriticConsensus
from paperorchestra.orchestra.verifier_item_helpers import _item, _safe_ref
from paperorchestra.orchestra.verifier_records import VerifierChecklistItem
from paperorchestra.orchestra.verifier_safety import _unsafe_reasons

ACCEPTED_CONSENSUS_BANDS = {"near_ready", "human_finalization_candidate", "ready_for_human_finalization", "ready"}


def _consensus_count_item(consensus: CriticConsensus | None) -> VerifierChecklistItem:
    if consensus is None:
        return _item("critic_consensus_two_or_more", "blocked", "provided_consensus_missing")
    if _unsafe_reasons(consensus.to_public_dict()):
        return _item("critic_consensus_two_or_more", "fail", "provided_consensus_public_payload_unsafe")
    if any(not verdict.valid for verdict in consensus.verdicts):
        return _item("critic_consensus_two_or_more", "fail", "critic_verdict_missing_evidence_links")
    if len(consensus.verdicts) < 2:
        return _item("critic_consensus_two_or_more", "blocked", "at_least_two_critic_verdicts_required")
    return _item(
        "critic_consensus_two_or_more",
        "pass",
        "provided_consensus_has_two_evidence_linked_verdicts",
        _safe_ref("critic_consensus", "artifacts/critic-consensus.json"),
    )


def _consensus_readiness_item(consensus: CriticConsensus | None) -> VerifierChecklistItem:
    if consensus is None:
        return _item("critic_consensus_near_ready_or_better", "blocked", "provided_consensus_missing")
    if _unsafe_reasons(consensus.to_public_dict()):
        return _item("critic_consensus_near_ready_or_better", "fail", "provided_consensus_public_payload_unsafe")
    if consensus.status == "failed":
        return _item("critic_consensus_near_ready_or_better", "fail", "provided_consensus_failed")
    if consensus.status != "pass":
        return _item("critic_consensus_near_ready_or_better", "blocked", "provided_consensus_not_final_or_needs_adjudication")
    if consensus.readiness_band in ACCEPTED_CONSENSUS_BANDS:
        return _item(
            "critic_consensus_near_ready_or_better",
            "pass",
            "provided_consensus_near_ready_or_better",
            _safe_ref("critic_consensus", "artifacts/critic-consensus.json"),
        )
    return _item("critic_consensus_near_ready_or_better", "blocked", "provided_consensus_below_near_ready")
