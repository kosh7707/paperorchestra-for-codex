from __future__ import annotations

from paperorchestra.orchestra.state import OrchestraState


class ReadinessPolicy:
    def apply(self, state: OrchestraState) -> OrchestraState:
        updated = state.clone()
        _append_hard_gate_failures(updated)
        _append_author_override_blocker(updated)
        _append_unique(updated.blocking_reasons, "missing_omx_invocation_evidence", updated.facets.omx == "required_missing")
        _append_unique(updated.blocking_reasons, "placeholder_figure_unresolved", updated.facets.figures == "placeholder_only")
        updated.refresh_derived_fields()
        return updated


def _append_hard_gate_failures(state: OrchestraState) -> None:
    if state.hard_gates.status != "fail":
        return
    for failure in state.hard_gates.failures:
        _append_unique(state.blocking_reasons, failure, True)


def _append_author_override_blocker(state: OrchestraState) -> None:
    conflicts = bool(state.author_override and (state.facets.claims == "conflict" or state.facets.evidence in {"unresolved", "blocked"}))
    _append_unique(state.blocking_reasons, "author_override_conflicts_with_evidence", conflicts)


def _append_unique(values: list[str], value: str, condition: bool) -> None:
    if condition and value not in values:
        values.append(value)
