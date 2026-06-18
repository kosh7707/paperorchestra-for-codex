from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
