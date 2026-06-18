from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session
# Compatibility facade: downstream operator modules import these answer
# metadata and issue-contract helpers from operator_contract.py.
from paperorchestra.feedback.operator_answer_metadata import (
    HUMAN_NEEDED_ANSWER_SCHEMA_VERSIONS,
    HUMAN_NEEDED_HANDOFF_TYPES,
    HUMAN_NEEDED_METADATA_ALLOWED_KEYS,
    HUMAN_NEEDED_METADATA_FORBIDDEN_KEYS,
    HUMAN_NEEDED_METADATA_SCHEMA_VERSION,
    HUMAN_NEEDED_PUBLIC_SCHEMA_VERSION,
    HUMAN_NEEDED_SELECTED_SOURCE_ALLOWED_KEYS,
    OPERATOR_FEEDBACK_INTENTS,
    _contains_forbidden_human_needed_metadata,
    _validate_human_needed_answer_metadata,
    validate_operator_review_notes,
)
from paperorchestra.feedback.operator_issue_contract import (
    ACTIONABLE_FAILURE_OWNER_CATEGORIES,
    OPERATOR_SOURCE,
    _action_for_issue,
    _normalize_issue_text,
    _normalize_operator_intent,
    _owner_category_for_issue,
    _validate_operator_issue,
    derive_operator_issue_id,
)
from paperorchestra.feedback.packet_artifacts import (
    _artifact_record,
    _file_sha256,
    _packet_sha256,
    _snapshot_operator_packet_artifacts,
)
from paperorchestra.feedback.packets import (
    _first_current_bound_existing,
    _first_existing,
    _operator_review_human_needed_artifacts,
    _packet_has_human_needed_context,
    _validate_operator_packet_artifact_bindings,
)
from paperorchestra.reviews.citation_integrity import citation_integrity_audit_path, citation_integrity_critic_path


OPERATOR_PACKET_SCHEMA_VERSION = "operator-review-packet/1"


OPERATOR_FEEDBACK_SCHEMA_VERSION = "operator-feedback/1"


OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION = "operator-feedback-import/1"


OPERATOR_FEEDBACK_EXECUTION_SCHEMA_VERSION = "operator-feedback-execution/1"


OPERATOR_FEEDBACK_INCORPORATION_SCHEMA_VERSION = "operator-feedback-incorporation/1"


OPERATOR_PUBLIC_ENTRYPOINTS = {
    "build-operator-review-packet",
    "import-operator-feedback",
    "apply-operator-feedback",
}


OVERALL_CATASTROPHIC_DROP = 8.0


AXIS_CATASTROPHIC_DROP = 15.0


HUMAN_REVIEWABLE_NEW_TIER2_CODES = {
    "citation_support_manual_check",
}


OPERATOR_REFINEMENT_FORBIDDEN_NEW_TIER2_CODES = {
    "citation_duplicate_support",
    "citation_integrity_failed",
    "citation_integrity_audit_fail",
    "citation_support_weak",
    "citation_support_manual_check",
    "citation_support_unsupported",
    "citation_support_contradicted",
    "citation_support_metadata_only",
    "citation_support_insufficient_evidence",
    "citation_support_evidence_missing",
    "high_risk_uncited_claim",
}


def _review_scope(require_pdf: bool, review_scope: str | None, pdf_path: str | Path | None) -> str:
    if review_scope:
        if review_scope not in {"pdf_and_tex", "tex_only"}:
            raise ContractError("review_scope must be one of: pdf_and_tex, tex_only")
        if review_scope == "pdf_and_tex" and not _file_sha256(pdf_path):
            raise ContractError("review_scope=pdf_and_tex requires a current compiled PDF")
        return review_scope
    return "pdf_and_tex" if require_pdf or _file_sha256(pdf_path) else "tex_only"


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
    artifacts: list[dict[str, Any]] = []
    required_paper = _artifact_record("paper_full_tex", paper_path, required=True)
    assert required_paper is not None
    artifacts.append(required_paper)
    if scope == "pdf_and_tex":
        pdf_record = _artifact_record("compiled_pdf", pdf_path, required=True)
        assert pdf_record is not None
        artifacts.append(pdf_record)
    for role, artifact_source_path in [
        (
            "citation_support_review",
            _first_current_bound_existing(
                "citation_support_review",
                manuscript_sha256,
                paper_dir / "citation_support_review.json",
                artifact_path(cwd, "citation_support_review.json"),
            ),
        ),
        (
            "section_review",
            _first_current_bound_existing(
                "section_review",
                manuscript_sha256,
                state.artifacts.latest_section_review_json,
                paper_dir / "section_review.json",
                artifact_path(cwd, "section_review.json"),
            ),
        ),
        (
            "quality_eval",
            _first_current_bound_existing(
                "quality_eval",
                manuscript_sha256,
                artifact_path(cwd, "quality-eval.json"),
            ),
        ),
        (
            "citation_integrity_audit",
            _first_current_bound_existing(
                "citation_integrity_audit",
                manuscript_sha256,
                citation_integrity_audit_path(cwd),
            ),
        ),
        (
            "citation_integrity_critic",
            _first_current_bound_existing(
                "citation_integrity_critic",
                manuscript_sha256,
                citation_integrity_critic_path(cwd),
            ),
        ),
        ("qa_loop_plan", qa_plan_path),
        ("qa_loop_execution", qa_execution_path),
        ("operator_feedback_execution", operator_execution_path),
        ("source_obligations", _first_existing(state.artifacts.source_obligations_json, artifact_path(cwd, "source_obligations.json"))),
        (
            "figure_placement_review",
            _first_current_bound_existing(
                "figure_placement_review",
                manuscript_sha256,
                state.artifacts.latest_figure_placement_review_json,
                artifact_path(cwd, "figure-placement-review.json"),
                artifact_path(cwd, "figure_placement_review.json"),
            ),
        ),
        ("ralph_brief", _first_existing(artifact_path(cwd, "ralph-brief.md"))),
        ("ralph_handoff", _first_existing(artifact_path(cwd, "ralph-handoff.json"))),
    ]:
        record = _artifact_record(role, artifact_source_path)
        if record:
            artifacts.append(record)
    artifacts = _snapshot_operator_packet_artifacts(packet_path, artifacts)

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
            "source": OPERATOR_SOURCE,
            "not_independent_human_review": True,
            "must_not_claim_independent_review": True,
        },
    }
    assert manuscript_sha256 is not None
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=manuscript_sha256,
    )
    packet["packet_sha256"] = _packet_sha256(packet)
    write_json(packet_path, packet)
    return packet_path, packet


def _read_packet(path: str | Path) -> dict[str, Any]:
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise ContractError("operator review packet must be a JSON object")
    if packet.get("schema_version") != OPERATOR_PACKET_SCHEMA_VERSION:
        raise ContractError("operator review packet has an unsupported schema_version")
    expected = _packet_sha256(packet)
    if packet.get("packet_sha256") != expected:
        raise ContractError("operator review packet hash does not match packet contents")
    for artifact in packet.get("artifacts") or []:
        if not isinstance(artifact, dict):
            raise ContractError("operator review packet artifact entry must be an object")
        actual = _file_sha256(artifact.get("path"))
        if not actual or actual != artifact.get("sha256"):
            raise ContractError(f"operator review packet artifact is missing or stale: {artifact.get('role')}")
    return packet


def import_operator_feedback(
    cwd: str | Path | None,
    *,
    packet_path: str | Path,
    feedback_path: str | Path,
    output_path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    packet_path = Path(packet_path).resolve()
    feedback_path = Path(feedback_path).resolve()
    packet = _read_packet(packet_path)
    if not _packet_has_human_needed_context(packet):
        raise ContractError(
            "operator review packet does not include terminal human_needed plan "
            "or latest human_needed QA/operator-feedback execution evidence"
        )
    _validate_operator_packet_artifact_bindings(
        cwd=cwd,
        packet=packet,
        current_manuscript_sha256=str(packet.get("manuscript_sha256") or ""),
    )
    feedback = read_json(feedback_path)
    if not isinstance(feedback, dict):
        raise ContractError("operator feedback must be a JSON object")
    if feedback.get("schema_version") != OPERATOR_FEEDBACK_SCHEMA_VERSION:
        raise ContractError("operator feedback has an unsupported schema_version")
    if feedback.get("source") != OPERATOR_SOURCE or feedback.get("not_independent_human_review") is not True:
        raise ContractError("operator feedback must be labeled source=codex_operator and not_independent_human_review=true")
    if feedback.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("operator feedback packet_sha256 does not match packet")
    if feedback.get("manuscript_sha256") != packet.get("manuscript_sha256"):
        raise ContractError("operator feedback manuscript_sha256 does not match packet")
    intent = _normalize_operator_intent(feedback)
    issues = feedback.get("issues")
    if not isinstance(issues, list) or not issues:
        raise ContractError("operator feedback must include one or more issues")
    imported_issues = [_validate_operator_issue(issue, packet) for issue in issues if isinstance(issue, dict)]
    if len(imported_issues) != len(issues):
        raise ContractError("operator feedback issues must all be JSON objects")
    human_needed_answer = _validate_human_needed_answer_metadata(
        feedback.get("human_needed_answer"),
        packet,
        {str(issue.get("id") or "") for issue in imported_issues},
        packet_path=packet_path,
        intent=intent,
        imported_issue_roles={str(issue.get("source_artifact_role") or "") for issue in imported_issues},
    )
    operator_review_notes = None
    if "operator_review_notes" in feedback:
        operator_review_notes = validate_operator_review_notes(feedback.get("operator_review_notes"))
    imported = {
        "schema_version": OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION,
        "imported_at": utc_now_iso(),
        "session_id": packet.get("session_id"),
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "packet_path": str(packet_path),
        "packet_sha256": packet.get("packet_sha256"),
        "feedback_path": str(feedback_path),
        "feedback_sha256": _file_sha256(feedback_path),
        "manuscript_sha256": packet.get("manuscript_sha256"),
        "review_scope": packet.get("review_scope"),
        "intent": intent,
        "issues": imported_issues,
        "translated_actions": [_action_for_issue(issue) for issue in imported_issues],
    }
    if isinstance(feedback.get("rendered_pdf_no_issues"), dict):
        imported["rendered_pdf_no_issues"] = dict(feedback["rendered_pdf_no_issues"])
    if operator_review_notes is not None:
        imported["operator_review_notes"] = operator_review_notes
    if human_needed_answer is not None:
        imported["human_needed_answer"] = human_needed_answer
    path = Path(output_path).resolve() if output_path else artifact_path(cwd, "operator_feedback.imported.json")
    write_json(path, imported)
    return path, imported


def _load_imported_feedback(imported_feedback_path: str | Path) -> dict[str, Any]:
    payload = read_json(imported_feedback_path)
    if not isinstance(payload, dict) or payload.get("schema_version") != OPERATOR_FEEDBACK_IMPORT_SCHEMA_VERSION:
        raise ContractError("imported operator feedback has an unsupported schema_version")
    if payload.get("source") != OPERATOR_SOURCE or payload.get("not_independent_human_review") is not True:
        raise ContractError("imported operator feedback lost non-independent provenance")
    packet = _read_packet(payload.get("packet_path"))
    if payload.get("packet_sha256") != packet.get("packet_sha256"):
        raise ContractError("imported operator feedback packet hash is stale")
    if "human_needed_answer" in payload:
        _validate_human_needed_answer_metadata(
            payload.get("human_needed_answer"),
            packet,
            {str(issue.get("id") or "") for issue in payload.get("issues") or [] if isinstance(issue, dict)},
            packet_path=payload.get("packet_path"),
            intent=str(payload.get("intent") or ""),
            imported_issue_roles={
                str(issue.get("source_artifact_role") or "")
                for issue in payload.get("issues") or []
                if isinstance(issue, dict)
            },
        )
    if "operator_review_notes" in payload:
        validate_operator_review_notes(payload.get("operator_review_notes"))
    return payload
