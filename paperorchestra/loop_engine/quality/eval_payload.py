from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.models import utc_now_iso
from paperorchestra.loop_engine.quality.policy import QUALITY_EVAL_SCHEMA_VERSION
from paperorchestra.loop_engine.quality.utils import _file_sha256, _sha256_jsonable
from paperorchestra.manuscript.source_obligations import source_obligations_path
from paperorchestra.reviews.citation_integrity_paths import (
    citation_integrity_audit_path,
    citation_integrity_critic_path,
    citation_intent_plan_path,
    citation_source_match_path,
)
from paperorchestra.reviews.citation_rendered_references import rendered_reference_audit_path
from paperorchestra.reviews.citation_quality import citation_quality_gate_path

def build_human_finalization_tier() -> dict[str, Any]:
    return {
        "status": "never_automated",
        "outstanding_owners": [
            {"area": "final_figures", "owner": "human"},
            {"area": "proof_rigor", "owner": "human"},
            {"area": "bibliography_curation", "owner": "human"},
            {"area": "venue_fit", "owner": "human"},
            {"area": "submission_decision", "owner": "human"},
        ],
    }


def build_quality_source_artifacts(
    *,
    cwd: str | Path | None,
    state,
    citation_support_review_path: str | Path,
    citation_support_review_sha256: str | None,
    ralph_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "paper_full_tex": state.artifacts.paper_full_tex,
        "reproducibility_audit": state.artifacts.latest_reproducibility_json,
        "fidelity_audit": state.artifacts.latest_fidelity_json,
        "figure_placement_review": state.artifacts.latest_figure_placement_review_json,
        "latest_validation": state.artifacts.latest_validation_json,
        "latest_review": state.artifacts.latest_review_json,
        "latest_section_review": getattr(state.artifacts, "latest_section_review_json", None),
        "narrative_plan": state.artifacts.narrative_plan_json,
        "claim_map": state.artifacts.claim_map_json,
        "citation_placement_plan": state.artifacts.citation_placement_plan_json,
        "source_obligations": str(source_obligations_path(cwd)),
        "citation_support_review": str(citation_support_review_path),
        "citation_review_sha256": citation_support_review_sha256,
        "citation_integrity_audit": str(citation_integrity_audit_path(cwd)),
        "citation_integrity_audit_sha256": _file_sha256(citation_integrity_audit_path(cwd)),
        "citation_integrity_critic": str(citation_integrity_critic_path(cwd)),
        "citation_integrity_critic_sha256": _file_sha256(citation_integrity_critic_path(cwd)),
        "citation_intent_plan": str(citation_intent_plan_path(cwd)),
        "citation_intent_plan_sha256": _file_sha256(citation_intent_plan_path(cwd)),
        "citation_source_match": str(citation_source_match_path(cwd)),
        "citation_source_match_sha256": _file_sha256(citation_source_match_path(cwd)),
        "rendered_reference_audit": str(rendered_reference_audit_path(cwd)),
        "rendered_reference_audit_sha256": _file_sha256(rendered_reference_audit_path(cwd)),
        "citation_quality_gate_sha256": _file_sha256(citation_quality_gate_path(cwd)),
        "ralph_handoff": ralph_evidence["ralph_handoff"],
        "ralph_handoff_sha256": ralph_evidence["ralph_handoff_sha256"],
        "qa_loop_history": ralph_evidence["qa_loop_history"],
        "qa_loop_history_sha256": ralph_evidence["qa_loop_history_sha256"],
    }


def build_quality_eval_payload(
    *,
    state,
    mode: str,
    manuscript_hash: str | None,
    provenance: dict[str, Any],
    non_reviewable: dict[str, Any],
    tiers: dict[str, Any],
    source_artifacts: dict[str, Any],
    reproducibility: dict[str, Any],
    fidelity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": QUALITY_EVAL_SCHEMA_VERSION,
        "manuscript_hash": f"sha256:{manuscript_hash}" if manuscript_hash else None,
        "evaluated_at": utc_now_iso(),
        "session_id": state.session_id,
        "mode": mode,
        "provenance_trust": provenance,
        "non_reviewable": non_reviewable,
        "tiers": tiers,
        "cross_iteration": {},
        "source_artifacts": source_artifacts,
        "audit_snapshot_hashes": {
            "reproducibility": f"sha256:{_sha256_jsonable(reproducibility)}",
            "fidelity": f"sha256:{_sha256_jsonable(fidelity)}",
        },
    }
