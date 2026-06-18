from __future__ import annotations

import re
from typing import Mapping

from paperorchestra.orchestra.scoring import ScholarlyScore, ScoringInputBundle
from paperorchestra.orchestra.verifier_item_helpers import _item, _safe_ref
from paperorchestra.orchestra.verifier_records import VerifierChecklistItem
from paperorchestra.orchestra.verifier_safety import _unsafe_reasons

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _scoring_bundle_item(scoring_bundle: ScoringInputBundle | None) -> VerifierChecklistItem:
    if scoring_bundle is None:
        return _item("scoring_bundle_complete", "blocked", "scoring_bundle_missing")
    payload = scoring_bundle.to_public_dict()
    unsafe = _unsafe_reasons(payload)
    if unsafe or payload.get("schema_version") != "scholarly-score-input-bundle/1":
        return _item("scoring_bundle_complete", "fail", "scoring_bundle_public_payload_unsafe_or_malformed")
    if not SHA256_RE.fullmatch(str(payload.get("manuscript_sha256", ""))):
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
    if _has_fail_closed_score_blocker(set(score.blocking_reasons)):
        return _item("score_valid_and_evidence_linked", "fail", "score_invalid_fail_closed")
    return _item("score_valid_and_evidence_linked", "blocked", "score_missing_repairable_evidence")


def _has_fail_closed_score_blocker(blockers: set[str]) -> bool:
    fail_prefixes = (
        "rejected_score_dimension:",
        "score_dimension_out_of_range:",
        "score_dimension_invalid_confidence:",
        "overall_score_out_of_range",
        "unknown_score_dimension:",
    )
    return any(reason == "overall_score_out_of_range" or reason.startswith(fail_prefixes) for reason in blockers)
