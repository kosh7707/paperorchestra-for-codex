from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping

SCHEMA_VERSION = "orchestrator-acceptance-ledger/1"
ACCEPTANCE_GATE_IDS: tuple[str, ...] = (
    "state_contract_tests",
    "action_planner_scenario_tests",
    "fake_omx_unit_contract_tests",
    "real_bounded_omx_command_probes",
    "mcp_raw_and_attach_smoke",
    "mock_demo",
    "compile_export",
    "fresh_container_functional_smoke",
    "private_final_live_smoke_redacted",
    "private_leakage_scan",
    "no_unsupported_critical_claims",
    "no_unknown_refs_for_critical_claims",
    "citation_integrity",
    "supplied_figures_inventoried_matched_or_blocked",
    "hard_gates_no_fail_except_human_polish",
    "critic_consensus_near_ready_or_better",
    "verifier_evidence_completeness_no_leakage",
    "exported_pdf_tex_evidence_bundle",
    "readme_environment_skill_docs_updated",
)

_GATE_TITLES: dict[str, str] = {
    "state_contract_tests": "State contract tests pass",
    "action_planner_scenario_tests": "Action planner scenario tests pass",
    "fake_omx_unit_contract_tests": "Fake OMX unit/contract tests pass",
    "real_bounded_omx_command_probes": "Real bounded OMX command probes pass or document blockers",
    "mcp_raw_and_attach_smoke": "MCP raw and Codex attach smoke passes",
    "mock_demo": "Mock demo still passes",
    "compile_export": "Compile/export still passes",
    "fresh_container_functional_smoke": "Fresh container functional smoke passes",
    "private_final_live_smoke_redacted": "Private final live smoke produced redacted evidence",
    "private_leakage_scan": "Private leakage scan passes",
    "no_unsupported_critical_claims": "No unsupported critical claims remain",
    "no_unknown_refs_for_critical_claims": "No Unknown references support critical claims",
    "citation_integrity": "Citation integrity passes or only non-critical warnings remain",
    "supplied_figures_inventoried_matched_or_blocked": "Supplied figures are inventoried/matched or explicitly blocked",
    "hard_gates_no_fail_except_human_polish": "Hard gates do not fail except final human-only polish",
    "critic_consensus_near_ready_or_better": "Critic consensus says near_ready or better",
    "verifier_evidence_completeness_no_leakage": "Verifier confirms evidence completeness and no leakage",
    "exported_pdf_tex_evidence_bundle": "Exported PDF, TeX, and evidence bundle exist",
    "readme_environment_skill_docs_updated": "README, ENVIRONMENT, and Skill docs explain runtime",
}

_ALLOWED_STATUSES = {"unknown", "blocked", "fail", "pass"}
_ALLOWED_EVIDENCE_KEYS = {"kind", "summary", "path", "sha256"}
_FORBIDDEN_KEYS = {"argv", "prompt", "raw_text", "executable_command"}
_PRIVATE_MARKERS = ("PRIVATE", "SECRET", "TOKEN")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_RAW_COMMAND_RE = re.compile(
    r"(?:^|\b)(?:run\s+)?omx\s+(?:status|trace|exec|ralph|autoresearch|sparkshell|doctor|state|explore|help|version|setup|update)\b",
    re.IGNORECASE,
)
REDACTED = "<redacted>"


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
        title = str(payload.get("title") or _GATE_TITLES.get(gate_id) or gate_id)
        status = str(payload.get("status", "unknown"))
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"Invalid acceptance gate status: {status}")
        evidence_refs = _validate_evidence_refs(payload.get("evidence_refs", []), gate_id=gate_id)
        notes = _validate_notes(payload.get("notes", []), gate_id=gate_id)
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
            raise ValueError("Acceptance ledger gate IDs do not match the v1 contract.")
        return cls(gates=gates, private_safe_summary=bool(payload.get("private_safe_summary", True)))


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
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"Invalid acceptance gate status for {gate_id}: {status}")
        evidence_refs = _validate_evidence_refs(entry.get("evidence_refs", []), gate_id=gate_id)
        notes = _validate_notes(entry.get("notes", []), gate_id=gate_id)
        gates.append(
            AcceptanceGate(
                id=gate_id,
                title=_GATE_TITLES[gate_id],
                status=status,
                evidence_refs=evidence_refs,
                notes=notes,
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


def _validate_evidence_refs(value: Any, *, gate_id: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"evidence_refs for {gate_id} must be a list.")
    refs: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"evidence_refs[{index}] for {gate_id} must be an object.")
        _reject_forbidden_keys(item, gate_id=gate_id)
        extra_keys = set(item) - _ALLOWED_EVIDENCE_KEYS
        if extra_keys:
            raise ValueError(f"Unsupported evidence ref key for {gate_id}: {sorted(extra_keys)[0]}")
        ref: dict[str, str] = {}
        for key in ("kind", "summary", "path", "sha256"):
            if key not in item or item[key] is None:
                continue
            if not isinstance(item[key], str):
                raise ValueError(f"evidence ref {key} for {gate_id} must be a string.")
            text = item[key]
            if key == "kind":
                _validate_kind(text, gate_id=gate_id)
            else:
                _validate_public_string(text, gate_id=gate_id, field=key)
            if key == "path":
                _validate_public_path(text, gate_id=gate_id)
            if key == "sha256" and text != REDACTED and not _SHA256_RE.fullmatch(text):
                raise ValueError(f"sha256 for {gate_id} must be 64 hex characters.")
            ref[key] = text
        refs.append(ref)
    return refs


def _validate_notes(value: Any, *, gate_id: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"notes for {gate_id} must be a list.")
    notes: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            _reject_forbidden_keys(item, gate_id=gate_id)
            raise ValueError(f"notes[{index}] for {gate_id} must be a string.")
        if not isinstance(item, str):
            raise ValueError(f"notes[{index}] for {gate_id} must be a string.")
        _validate_public_string(item, gate_id=gate_id, field="notes")
        notes.append(item)
    return notes


def _reject_forbidden_keys(value: Mapping[str, Any], *, gate_id: str) -> None:
    for key, item in value.items():
        if str(key) in _FORBIDDEN_KEYS:
            raise ValueError(f"Unsafe evidence key for {gate_id}: {key}")
        if isinstance(item, Mapping):
            _reject_forbidden_keys(item, gate_id=gate_id)


def _validate_public_string(value: str, *, gate_id: str, field: str) -> None:
    if value == REDACTED:
        return
    upper = value.upper()
    if any(marker in upper for marker in _PRIVATE_MARKERS):
        raise ValueError(f"Unsafe private marker in {field} for {gate_id}.")
    if _RAW_COMMAND_RE.search(value):
        raise ValueError(f"Unsafe raw command text in {field} for {gate_id}.")
    if _looks_like_absolute_path(value):
        raise ValueError(f"Unsafe absolute path in {field} for {gate_id}.")


def _validate_kind(value: str, *, gate_id: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_/-]*", value):
        raise ValueError(f"Unsafe evidence kind for {gate_id}.")


def _validate_public_path(value: str, *, gate_id: str) -> None:
    if value == REDACTED:
        return
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Evidence path for {gate_id} must be workspace-relative and contained.")


def _looks_like_absolute_path(value: str) -> bool:
    return value.startswith("/") or bool(re.search(r"\s/[A-Za-z0-9_.-]", value))
