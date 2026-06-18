from __future__ import annotations

from paperorchestra.orchestra.state import OrchestraState
from paperorchestra.orchestra.verifier_item_helpers import _item
from paperorchestra.orchestra.verifier_records import VerifierChecklistItem


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
