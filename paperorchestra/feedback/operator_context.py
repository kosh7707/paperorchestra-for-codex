from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import sanitize_author_facing_text
from paperorchestra.core.io import write_json
from paperorchestra.core.session import artifact_path
from paperorchestra.feedback.operator_contract import _read_packet
from paperorchestra.feedback.operator_issue_contract import OPERATOR_SOURCE
from paperorchestra.feedback.operator_contexts import citations as _citations
from paperorchestra.feedback.operator_contexts import claims as _claims
from paperorchestra.feedback.operator_contexts import figures as _figures
from paperorchestra.feedback.operator_contexts import packet as _packet
from paperorchestra.feedback.operator_contexts.prior_attempts import _compact_prior_rejected_attempts
from paperorchestra.feedback.operator_contexts.refinement_constraints import _operator_refinement_constraints


def _operator_review_payload(imported: dict[str, Any], *, prior_attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issues = imported.get("issues") or []
    top_improvements = [
        f"[{issue.get('id')}] "
        + sanitize_author_facing_text(issue.get("suggested_action"), fallback="Revise the target section using ordinary scholarly prose.")
        for issue in issues
    ]
    weaknesses = [
        f"[{issue.get('id')}] "
        + sanitize_author_facing_text(issue.get("rationale"), fallback="The target section needs ordinary scholarly revision.")
        for issue in issues
    ]
    issue_context = _operator_issue_context(imported, prior_attempts=prior_attempts)
    return {
        "schema_version": "operator-feedback-review/1",
        "source": OPERATOR_SOURCE,
        "not_independent_human_review": True,
        "manuscript_sha256": imported.get("manuscript_sha256"),
        "packet_sha256": imported.get("packet_sha256"),
        "summary": {"weaknesses": weaknesses, "top_improvements": top_improvements},
        "issue_context": issue_context,
        "questions": [],
        "penalties": [],
        "axis_scores": {},
        "writer_blind_to_reviewer_scores": True,
        "score_redaction": "operator feedback is issue-shaped and contains no reviewer scores",
    }


def _operator_issue_context(imported: dict[str, Any], *, prior_attempts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Attach concrete failing claim context to operator feedback for the writer.

    Human/operator feedback enters the refiner through the review JSON surface.
    The imported issue list is intentionally terse, so without this context the
    writer sees only abstract instructions such as "fix weak citation support"
    and cannot target the actual sentences that failed the critics.
    """
    packet_path = imported.get("packet_path")
    if not packet_path:
        return {}
    try:
        packet = _read_packet(packet_path)
    except Exception:
        return {}
    citation_review = _packet._packet_payload_by_role(packet, "citation_support_review")
    quality_eval = _packet._packet_payload_by_role(packet, "quality_eval")
    citation_integrity_audit = _packet._packet_payload_by_role(packet, "citation_integrity_audit")
    figure_placement_review = _packet._packet_payload_by_role(packet, "figure_placement_review")
    prior_rejected_attempts = _compact_prior_rejected_attempts(prior_attempts)
    protected_supported = _citations._protected_supported_citation_context(citation_review, citation_integrity_audit)
    context = {
        "problematic_citation_items": _citations._problematic_citation_context(citation_review),
        "high_risk_uncited_claims": _claims._high_risk_claim_context(quality_eval),
        "citation_density_issues": _citations._citation_density_context(citation_integrity_audit),
        "citation_duplicate_support_issues": _citations._duplicate_support_context(citation_integrity_audit, citation_review),
        "figure_placement_issues": _figures._figure_issue_context(figure_placement_review),
        "refinement_constraints": _operator_refinement_constraints(quality_eval, citation_integrity_audit),
        "writer_instruction": (
            "Use these concrete sentences as the primary repair targets. Do not add new bibliography keys; "
            "either ground each sentence with existing directly supporting evidence, soften it into scoped author-material prose, or remove it. "
            "A candidate that uses dense citation bundles to hide weak support, weak citation support, duplicate support, or high-risk uncited claims will be rejected. "
            "Preserve protected_supported_citation_items exactly unless an active issue explicitly targets that item, anchor, sentence, or duplicate/density citation key."
        ),
    }
    if protected_supported:
        context["protected_supported_citation_items"] = protected_supported
    if prior_rejected_attempts:
        context["prior_rejected_attempts"] = prior_rejected_attempts
        context["prior_rejection_instruction"] = (
            "Do not repeat prior rejected repair shapes. If a prior attempt regressed active Tier-2 metrics, "
            "the next candidate must either reduce those active metrics without new regressions or leave the issue for human_needed."
        )
    return {key: value for key, value in context.items() if value}


def _write_operator_review_for_refiner(
    cwd: str | Path | None,
    imported: dict[str, Any],
    *,
    prior_attempts: list[dict[str, Any]] | None = None,
) -> Path:
    path = artifact_path(cwd, "operator_feedback.redacted_review.json")
    write_json(path, _operator_review_payload(imported, prior_attempts=prior_attempts))
    return path
