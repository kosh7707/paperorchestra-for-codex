from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from paperorchestra.orchestra.acceptance_contract import (
    ACCEPTANCE_GATE_IDS,
    ALLOWED_STATUSES,
    GATE_TITLES,
    SCHEMA_VERSION,
    _ALLOWED_EVIDENCE_KEYS,
)
from paperorchestra.orchestra.acceptance_validation import validate_evidence_refs, validate_notes


@dataclass(frozen=True)
class AcceptanceGate:
    id: str
    title: str
    status: str = "unknown"
    required: bool = True
    evidence_refs: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    private_safe_summary: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "required": self.required,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "notes": list(self.notes),
            "private_safe_summary": self.private_safe_summary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AcceptanceGate":
        gate_id = str(payload["id"])
        title = str(payload.get("title") or GATE_TITLES.get(gate_id) or gate_id)
        status = str(payload.get("status", "unknown"))
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid acceptance gate status: {status}")
        evidence_refs = validate_evidence_refs(payload.get("evidence_refs", []), gate_id=gate_id)
        notes = validate_notes(payload.get("notes", []), gate_id=gate_id)
        return cls(
            id=gate_id,
            title=title,
            status=status,
            required=bool(payload.get("required", True)),
            evidence_refs=evidence_refs,
            notes=notes,
            private_safe_summary=bool(payload.get("private_safe_summary", True)),
        )


@dataclass(frozen=True)
class AcceptanceLedger:
    gates: list[AcceptanceGate]
    schema_version: str = SCHEMA_VERSION
    private_safe_summary: bool = True

    @property
    def gate_count(self) -> int:
        return len(self.gates)

    @property
    def overall_status(self) -> str:
        statuses = [gate.status for gate in self.gates]
        if "fail" in statuses:
            return "failed"
        if "blocked" in statuses:
            return "blocked"
        if "unknown" in statuses:
            return "unknown"
        return "pass"

    @property
    def missing_gate_ids(self) -> list[str]:
        return [gate.id for gate in self.gates if gate.status == "unknown"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "overall_status": self.overall_status,
            "gate_count": self.gate_count,
            "gates": [gate.to_dict() for gate in self.gates],
            "missing_gate_ids": self.missing_gate_ids,
            "private_safe_summary": self.private_safe_summary,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AcceptanceLedger":
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Invalid acceptance ledger schema_version.")
        gates_payload = payload.get("gates")
        if not isinstance(gates_payload, list):
            raise ValueError("Acceptance ledger gates must be a list.")
        gates = [AcceptanceGate.from_dict(item) for item in gates_payload]
        gate_ids = tuple(gate.id for gate in gates)
        if gate_ids != ACCEPTANCE_GATE_IDS:
            raise ValueError("Acceptance ledger gate IDs do not match the v2 contract.")
        return cls(gates=gates, private_safe_summary=bool(payload.get("private_safe_summary", True)))


__all__ = [
    "ACCEPTANCE_GATE_IDS",
    "ALLOWED_STATUSES",
    "GATE_TITLES",
    "SCHEMA_VERSION",
    "AcceptanceGate",
    "AcceptanceLedger",
    "_ALLOWED_EVIDENCE_KEYS",
    "validate_evidence_refs",
    "validate_notes",
]
