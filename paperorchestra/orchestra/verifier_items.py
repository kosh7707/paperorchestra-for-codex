from __future__ import annotations

import re
from typing import Mapping

from paperorchestra.orchestra.consensus import CriticConsensus
from paperorchestra.orchestra.scoring import ScholarlyScore, ScoringInputBundle
from paperorchestra.orchestra.state import OrchestraState

from .verifier_records import VerifierChecklistItem
from .verifier_safety import _unsafe_reasons

ACCEPTED_CONSENSUS_BANDS = {"near_ready", "human_finalization_candidate", "ready_for_human_finalization", "ready"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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


def _scoring_bundle_item(scoring_bundle: ScoringInputBundle | None) -> VerifierChecklistItem:
    if scoring_bundle is None:
        return _item("scoring_bundle_complete", "blocked", "scoring_bundle_missing")
    payload = scoring_bundle.to_public_dict()
    unsafe = _unsafe_reasons(payload)
    if unsafe or payload.get("schema_version") != "scholarly-score-input-bundle/1":
        return _item("scoring_bundle_complete", "fail", "scoring_bundle_public_payload_unsafe_or_malformed")
    if not _SHA256_RE.fullmatch(str(payload.get("manuscript_sha256", ""))):
        return _item("scoring_bundle_complete", "fail", "scoring_bundle_manuscript_hash_invalid")
    required_artifacts = payload.get("required_artifacts")
    if not isinstance(required_artifacts, Mapping) or not required_artifacts:
        return _item("scoring_bundle_complete", "blocked", "scoring_bundle_required_artifacts_missing")
    if any(not isinstance(ref, str) or not ref for ref in required_artifacts.values()):
        return _item("scoring_bundle_complete", "blocked", "scoring_bundle_required_artifact_ref_missing")
    if payload.get("complete") is True:
        return _item("scoring_bundle_complete", "pass", "scoring_bundle_complete", _safe_ref("score_bundle", "artifacts/score-input.json"))
    return _item("scoring_bundle_complete", "blocked", "scoring_bundle_incomplete")


def _score_item(score: ScholarlyScore | None) -> VerifierChecklistItem:
    if score is None:
        return _item("score_valid_and_evidence_linked", "blocked", "score_missing")
    payload = score.to_public_dict()
    unsafe = _unsafe_reasons(payload)
    if unsafe:
        return _item("score_valid_and_evidence_linked", "fail", "score_public_payload_unsafe")
    if score.valid:
        return _item("score_valid_and_evidence_linked", "pass", "score_valid_and_evidence_linked", _safe_ref("score", "artifacts/score.json"))
    blockers = set(score.blocking_reasons)
    fail_prefixes = (
        "rejected_score_dimension:",
        "score_dimension_out_of_range:",
        "score_dimension_invalid_confidence:",
        "overall_score_out_of_range",
        "unknown_score_dimension:",
    )
    if any(reason == "overall_score_out_of_range" or reason.startswith(fail_prefixes) for reason in blockers):
        return _item("score_valid_and_evidence_linked", "fail", "score_invalid_fail_closed")
    return _item("score_valid_and_evidence_linked", "blocked", "score_missing_repairable_evidence")


def _consensus_count_item(consensus: CriticConsensus | None) -> VerifierChecklistItem:
    if consensus is None:
        return _item("critic_consensus_two_or_more", "blocked", "provided_consensus_missing")
    if _unsafe_reasons(consensus.to_public_dict()):
        return _item("critic_consensus_two_or_more", "fail", "provided_consensus_public_payload_unsafe")
    if any(not verdict.valid for verdict in consensus.verdicts):
        return _item("critic_consensus_two_or_more", "fail", "critic_verdict_missing_evidence_links")
    if len(consensus.verdicts) < 2:
        return _item("critic_consensus_two_or_more", "blocked", "at_least_two_critic_verdicts_required")
    return _item("critic_consensus_two_or_more", "pass", "provided_consensus_has_two_evidence_linked_verdicts", _safe_ref("critic_consensus", "artifacts/critic-consensus.json"))


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
        return _item("critic_consensus_near_ready_or_better", "pass", "provided_consensus_near_ready_or_better", _safe_ref("critic_consensus", "artifacts/critic-consensus.json"))
    return _item("critic_consensus_near_ready_or_better", "blocked", "provided_consensus_below_near_ready")


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


def _item(item_id: str, status: str, reason: str, *refs: dict[str, str]) -> VerifierChecklistItem:
    return VerifierChecklistItem(id=item_id, status=status, reason=reason, evidence_refs=list(refs), private_safe=True)


def _safe_ref(kind: str, path: str) -> dict[str, str]:
    return {"kind": kind, "path": path}
