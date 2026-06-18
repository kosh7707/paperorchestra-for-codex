from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.orchestra.consensus import CriticConsensus
from paperorchestra.orchestra.controller import inspect_state as orchestrator_inspect_state
from paperorchestra.orchestra.scoring import ScholarlyScore, ScoringInputBundle
from paperorchestra.orchestra.state import OrchestraState

from .verifier_items import build_verifier_items
from .verifier_records import (
    VERIFIER_CHECKLIST_FILENAME,
    VERIFIER_CHECKLIST_ITEM_IDS,
    VERIFIER_CHECKLIST_SCHEMA_VERSION,
    VerifierChecklistItem,
    VerifierEvidenceChecklist,
    verifier_acceptance_evidence,
)
from .verifier_safety import _redacted_label, _unsafe_reasons


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
    items = build_verifier_items(
        state,
        scoring_bundle,
        score,
        consensus,
        compiled=compiled,
        exported=exported,
        unsafe_reasons=unsafe_reasons,
    )
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


__all__ = [
    "VERIFIER_CHECKLIST_FILENAME",
    "VERIFIER_CHECKLIST_ITEM_IDS",
    "VERIFIER_CHECKLIST_SCHEMA_VERSION",
    "VerifierChecklistItem",
    "VerifierEvidenceChecklist",
    "build_verifier_evidence_checklist",
    "verifier_acceptance_evidence",
    "verifier_evidence_checklist_path",
    "write_verifier_evidence_checklist",
]
