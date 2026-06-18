from __future__ import annotations

from typing import Any, Mapping

from paperorchestra.orchestra.acceptance_records import (
    ACCEPTANCE_GATE_IDS,
    ALLOWED_STATUSES,
    GATE_TITLES as _GATE_TITLES,
    SCHEMA_VERSION,
    AcceptanceGate,
    AcceptanceLedger,
    validate_evidence_refs,
    validate_notes,
)


def build_acceptance_ledger(evidence: Mapping[str, Any] | None = None) -> AcceptanceLedger:
    evidence = evidence or {}
    if not isinstance(evidence, Mapping):
        raise ValueError("Acceptance evidence must be an object keyed by gate id.")
    unknown_ids = sorted(set(evidence) - set(ACCEPTANCE_GATE_IDS))
    if unknown_ids:
        raise ValueError(f"Unknown acceptance gate id: {unknown_ids[0]}")

    gates: list[AcceptanceGate] = []
    for gate_id in ACCEPTANCE_GATE_IDS:
        entry = evidence.get(gate_id)
        if entry is None:
            gates.append(AcceptanceGate(id=gate_id, title=_GATE_TITLES[gate_id]))
            continue
        if not isinstance(entry, Mapping):
            raise ValueError(f"Acceptance evidence for {gate_id} must be an object.")
        status = str(entry.get("status", "unknown"))
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid acceptance gate status for {gate_id}: {status}")
        gates.append(
            AcceptanceGate(
                id=gate_id,
                title=_GATE_TITLES[gate_id],
                status=status,
                evidence_refs=validate_evidence_refs(entry.get("evidence_refs", []), gate_id=gate_id),
                notes=validate_notes(entry.get("notes", []), gate_id=gate_id),
            )
        )
    return AcceptanceLedger(gates=gates)


def render_acceptance_ledger_summary(ledger: AcceptanceLedger) -> str:
    counts = {"pass": 0, "fail": 0, "blocked": 0, "unknown": 0}
    for gate in ledger.gates:
        counts[gate.status] = counts.get(gate.status, 0) + 1
    first_open = [gate.id for gate in ledger.gates if gate.status in {"blocked", "fail", "unknown"}][:5]
    lines = [
        "Acceptance ledger",
        f"overall: {ledger.overall_status}",
        f"gates: {ledger.gate_count}",
        f"pass: {counts['pass']}",
        f"fail: {counts['fail']}",
        f"blocked: {counts['blocked']}",
        f"unknown: {counts['unknown']}",
    ]
    if first_open:
        lines.append("first open gates:")
        lines.extend(f"  - {gate_id}" for gate_id in first_open)
    return "\n".join(lines)
