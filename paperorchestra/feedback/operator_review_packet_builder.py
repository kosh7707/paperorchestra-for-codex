from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.feedback import operator_issue_contract as _issues
from paperorchestra.feedback.operator_contract_constants import OPERATOR_PACKET_SCHEMA_VERSION
from paperorchestra.feedback.operator_packet_artifact_sources import (
    _operator_packet_artifacts,
    _optional_packet_artifact_sources,
)
from paperorchestra.feedback.operator_review_scope import _review_scope
from paperorchestra.feedback.packet_artifacts import _file_sha256, _packet_sha256
from paperorchestra.feedback.packet_artifact_validation import _validate_operator_packet_artifact_bindings
from paperorchestra.feedback.packet_discovery import _operator_review_human_needed_artifacts


def build_operator_review_packet(
    cwd: str | Path | None,
    *,
    output_path: str | Path | None = None,
    require_pdf: bool = False,
    review_scope: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Build the hash-bound packet an external OMX/Codex operator must review."""

    state = load_session(cwd)
    if not state.artifacts.paper_full_tex:
        raise ContractError("Need paper.full.tex before building an operator review packet.")
    paper_path = Path(state.artifacts.paper_full_tex).resolve()
    if not paper_path.exists():
        raise ContractError(f"paper.full.tex is missing: {paper_path}")
    paper_dir = paper_path.parent
    qa_plan_path, qa_execution_path, operator_execution_path = _operator_review_human_needed_artifacts(cwd)
    pdf_path = state.artifacts.compiled_pdf
    scope = _review_scope(require_pdf, review_scope, pdf_path)
    if require_pdf and scope != "pdf_and_tex":
        raise ContractError("require_pdf=True requires review_scope=pdf_and_tex")
    packet_path = Path(output_path).resolve() if output_path else artifact_path(cwd, "operator_review_packet.json")

    manuscript_sha256 = _file_sha256(paper_path)
    artifacts = _operator_packet_artifacts(
        cwd=cwd,
        state=state,
        packet_path=packet_path,
        scope=scope,
        paper_path=paper_path,
        paper_dir=paper_dir,
        pdf_path=pdf_path,
        manuscript_sha256=manuscript_sha256,
        qa_plan_path=qa_plan_path,
        qa_execution_path=qa_execution_path,
        operator_execution_path=operator_execution_path,
    )
    packet: dict[str, Any] = {
        "schema_version": OPERATOR_PACKET_SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "session_id": state.session_id,
        "manuscript_sha256": manuscript_sha256,
        "review_scope": scope,
        "review_scope_rationale": "compiled PDF present and included" if scope == "pdf_and_tex" else "TeX-only operator review; compiled PDF absent or not required",
        "artifacts": artifacts,
        "operator_instructions": {
            "feedback_authoring": "external_omx_side",
            "source": _issues.OPERATOR_SOURCE,
            "not_independent_human_review": True,
            "must_not_claim_independent_review": True,
        },
    }
    assert manuscript_sha256 is not None
    _validate_operator_packet_artifact_bindings(cwd=cwd, packet=packet, current_manuscript_sha256=manuscript_sha256)
    packet["packet_sha256"] = _packet_sha256(packet)
    write_json(packet_path, packet)
    return packet_path, packet


__all__ = [
    "_operator_packet_artifacts",
    "_optional_packet_artifact_sources",
    "_review_scope",
    "build_operator_review_packet",
]
