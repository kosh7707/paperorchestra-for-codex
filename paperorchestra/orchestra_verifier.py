from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .io_utils import write_json
from .orchestra_consensus import CriticConsensus
from .orchestra_scoring import ScholarlyScore, ScoringInputBundle
from .orchestra_state import OrchestraState
from .orchestrator import inspect_state as orchestrator_inspect_state
from .session import artifact_path

VERIFIER_CHECKLIST_SCHEMA_VERSION = "verifier-evidence-checklist/1"
VERIFIER_CHECKLIST_FILENAME = "verifier_evidence_checklist.json"
VERIFIER_CHECKLIST_ITEM_IDS: tuple[str, ...] = (
    "scoring_bundle_complete",
    "score_valid_and_evidence_linked",
    "critic_consensus_two_or_more",
    "critic_consensus_near_ready_or_better",
    "hard_gates_no_fail",
    "compile_export_accounted_for",
    "public_safety_no_raw_private_evidence",
)
ACCEPTED_CONSENSUS_BANDS = {"near_ready", "human_finalization_candidate", "ready_for_human_finalization", "ready"}
_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")
_FORBIDDEN_KEYS = {"argv", "prompt", "raw_text", "executable_command"}
_RAW_COMMAND_RE = re.compile(r"(?:^|\b)omx\s+(?:status|trace|exec|ralph|autoresearch|sparkshell|doctor|state|explore|help|version|setup|update)\b", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class VerifierChecklistItem:
    id: str
    status: str
    reason: str
    evidence_refs: list[dict[str, str]] = field(default_factory=list)
    private_safe: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "reason": self.reason,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "private_safe": self.private_safe,
        }


@dataclass(frozen=True)
class VerifierEvidenceChecklist:
    items: list[VerifierChecklistItem]
    output_label: str | None = None
    private_safe_summary: bool = True

    @property
    def overall_status(self) -> str:
        statuses = [item.status for item in self.items]
        if "fail" in statuses:
            return "fail"
        if "blocked" in statuses:
            return "blocked"
        return "pass"

    def item_status(self, item_id: str) -> str:
        for item in self.items:
            if item.id == item_id:
                return item.status
        raise KeyError(item_id)

    def to_public_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": VERIFIER_CHECKLIST_SCHEMA_VERSION,
            "overall_status": self.overall_status,
            "items": [item.to_public_dict() for item in self.items],
            "acceptance_evidence": verifier_acceptance_evidence(self)["verifier_evidence_completeness_no_leakage"],
            "private_safe_summary": self.private_safe_summary,
        }
        if self.output_label:
            payload["output_label"] = self.output_label
        return payload


def verifier_evidence_checklist_path(cwd: str | Path | None = None) -> Path:
    return artifact_path(cwd, VERIFIER_CHECKLIST_FILENAME)


def build_verifier_evidence_checklist(
    state: OrchestraState,
    scoring_bundle: ScoringInputBundle | None,
    score: ScholarlyScore | None,
    consensus: CriticConsensus | None,
    *,
    compiled: bool = False,
    exported: bool = False,
    artifact_refs: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> VerifierEvidenceChecklist:
    unsafe_reasons = _unsafe_reasons(artifact_refs or {})
    items = [
        _scoring_bundle_item(scoring_bundle),
        _score_item(score),
        _consensus_count_item(consensus),
        _consensus_readiness_item(consensus),
        _hard_gate_item(state),
        _compile_export_item(compiled=compiled, exported=exported, unsafe=bool(unsafe_reasons)),
        _public_safety_item(unsafe_reasons),
    ]
    output_label = _redacted_label("verifier-output", str(Path(output_path).expanduser().resolve())) if output_path else None
    return VerifierEvidenceChecklist(items=items, output_label=output_label, private_safe_summary=True)


def write_verifier_evidence_checklist(
    cwd: str | Path | None = None,
    *,
    output_path: str | Path | None = None,
    state: OrchestraState | None = None,
    scoring_bundle: ScoringInputBundle | None = None,
    score: ScholarlyScore | None = None,
    consensus: CriticConsensus | None = None,
    compiled: bool = False,
    exported: bool = False,
    artifact_refs: Mapping[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    state = state or orchestrator_inspect_state(cwd)
    path = Path(output_path).expanduser().resolve() if output_path else verifier_evidence_checklist_path(cwd)
    checklist = build_verifier_evidence_checklist(
        state,
        scoring_bundle,
        score,
        consensus,
        compiled=compiled,
        exported=exported,
        artifact_refs=artifact_refs,
        output_path=path,
    )
    payload = checklist.to_public_dict()
    write_json(path, payload)
    return path, payload


def verifier_acceptance_evidence(checklist: VerifierEvidenceChecklist) -> dict[str, dict[str, Any]]:
    status = checklist.overall_status
    return {
        "verifier_evidence_completeness_no_leakage": {
            "status": status,
            "evidence_refs": [
                {
                    "kind": "verifier/checklist",
                    "summary": f"verifier checklist {status}",
                    "path": f"artifacts/{VERIFIER_CHECKLIST_FILENAME}",
                }
            ],
            "notes": ["public-safe verifier evidence checklist"],
        }
    }


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


def _unsafe_reasons(value: Any) -> list[str]:
    reasons: list[str] = []

    def visit(node: Any, *, key: str | None = None) -> None:
        if key in _FORBIDDEN_KEYS:
            reasons.append("forbidden_key")
            return
        if isinstance(node, Mapping):
            for child_key, child_value in node.items():
                visit(child_value, key=str(child_key))
            return
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, str):
            return
        upper = node.upper()
        if any(marker in upper for marker in _PRIVATE_MARKERS):
            reasons.append("private_marker")
        elif _looks_like_absolute_path(node):
            reasons.append("absolute_path")
        elif _RAW_COMMAND_RE.search(node):
            reasons.append("raw_command")

    visit(value)
    return sorted(set(reasons))


def _looks_like_absolute_path(value: str) -> bool:
    return value.startswith("/") or bool(re.search(r"\s/[A-Za-z0-9_.-]", value))


def _redacted_label(kind: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
    return f"redacted-{kind}:{digest[:12]}"
