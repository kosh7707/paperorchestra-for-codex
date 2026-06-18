from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json
from paperorchestra.engine.review_stages import (
    compile_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.loop_engine.quality.loop import write_quality_eval, write_quality_loop_plan
from paperorchestra.reviews.citation_integrity import write_citation_integrity_audit
from paperorchestra.reviews.citation_integrity_gate import write_citation_integrity_critic
from paperorchestra.reviews.citation_rendered_references import write_rendered_reference_audit
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.runtime.provider_base import BaseProvider
from paperorchestra.runtime.provider_registry import get_citation_support_provider


def _verification_snapshot(
    cwd: str | Path | None,
    *,
    provider: BaseProvider,
    require_compile: bool,
    quality_mode: str,
    max_iterations: int,
    require_live_verification: bool,
    accept_mixed_provenance: bool,
    runtime_mode: str,
    citation_evidence_mode: str,
    citation_provider_name: str | None,
    citation_provider_command: str | None,
    validation_name: str,
) -> dict[str, Any]:
    validation_path, validation_payload = record_current_validation_report(cwd, name=validation_name)
    compile_payload: dict[str, Any] | None = None
    if require_compile:
        try:
            pdf_path = compile_current_paper(cwd)
            compile_payload = {"ok": True, "pdf": str(pdf_path)}
        except Exception as exc:  # pragma: no cover - compile depends on local toolchain
            compile_payload = {"ok": False, "error": str(exc)}
    citation_provider = get_citation_support_provider(
        citation_provider_name or ("mock" if citation_evidence_mode == "heuristic" else "shell"),
        command=citation_provider_command,
        evidence_mode=citation_evidence_mode,
    )
    section_path = write_section_review(cwd)
    figure_path, figure_payload = write_figure_placement_review(cwd)
    citation_path = write_citation_support_review(cwd, provider=citation_provider, evidence_mode=citation_evidence_mode)
    review_path = review_current_paper(cwd, provider, runtime_mode=runtime_mode)
    write_rendered_reference_audit(cwd, quality_mode=quality_mode)
    write_citation_integrity_audit(cwd, quality_mode=quality_mode)
    write_citation_integrity_critic(cwd, quality_mode=quality_mode)
    quality_path, quality_eval = write_quality_eval(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
    )
    plan_path, plan = write_quality_loop_plan(
        cwd,
        quality_mode=quality_mode,
        max_iterations=max_iterations,
        require_live_verification=require_live_verification,
        accept_mixed_provenance=accept_mixed_provenance,
        quality_eval_input_path=quality_path,
    )
    return {
        "validation_path": validation_path,
        "validation_payload": validation_payload,
        "compile_payload": compile_payload,
        "section_path": section_path,
        "figure_path": figure_path,
        "figure_payload": figure_payload,
        "citation_path": citation_path,
        "review_path": review_path,
        "quality_path": quality_path,
        "quality_eval": quality_eval,
        "plan_path": plan_path,
        "plan": plan,
    }


def _verification_block(verification: dict[str, Any]) -> dict[str, Any]:
    plan = verification.get("plan") or {}
    quality_eval = verification.get("quality_eval") if isinstance(verification.get("quality_eval"), dict) else {}
    source_artifacts = quality_eval.get("source_artifacts") if isinstance(quality_eval.get("source_artifacts"), dict) else {}
    citation_integrity_critic_payload: dict[str, Any] = {}
    citation_integrity_critic_path = source_artifacts.get("citation_integrity_critic")
    if citation_integrity_critic_path:
        try:
            payload = read_json(citation_integrity_critic_path)
            if isinstance(payload, dict):
                citation_integrity_critic_payload = payload
        except Exception:
            citation_integrity_critic_payload = {}
    citation_check = {}
    tiers = quality_eval.get("tiers") if isinstance(quality_eval.get("tiers"), dict) else {}
    tier2 = tiers.get("tier_2_claim_safety") if isinstance(tiers.get("tier_2_claim_safety"), dict) else {}
    checks = tier2.get("checks") if isinstance(tier2.get("checks"), dict) else {}
    if isinstance(checks.get("citation_support_critic"), dict):
        citation_check = checks["citation_support_critic"]
    return {
        "validate_current": {
            "path": str(verification["validation_path"]),
            "ok": verification["validation_payload"].get("ok"),
        },
        "compile": verification.get("compile_payload"),
        "section_review": {"path": str(verification["section_path"])},
        "figure_placement_review": {
            "path": str(verification["figure_path"]),
            "manuscript_sha256": (verification.get("figure_payload") or {}).get("manuscript_sha256"),
        },
        "citation_support_review": {
            "path": str(verification["citation_path"]),
            "sha256": source_artifacts.get("citation_review_sha256") or citation_check.get("citation_review_sha256"),
            "summary": citation_check.get("canonical_summary") or citation_check.get("summary"),
        },
        "citation_integrity_critic": {
            "path": citation_integrity_critic_path,
            "sha256": source_artifacts.get("citation_integrity_critic_sha256"),
            "status": citation_integrity_critic_payload.get("status"),
            "manuscript_sha256": citation_integrity_critic_payload.get("manuscript_sha256"),
            "failing_codes": citation_integrity_critic_payload.get("failing_codes"),
        },
        "review": {"path": str(verification["review_path"])},
        "quality_eval": {
            "path": str(verification["quality_path"]),
            "citation_review_sha256": source_artifacts.get("citation_review_sha256"),
        },
        "qa_loop_plan": {"path": str(verification["plan_path"]), "verdict": plan.get("verdict")},
    }
