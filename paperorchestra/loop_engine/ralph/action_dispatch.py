from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paperorchestra.core.session import artifact_path, load_session
from paperorchestra.engine.pipeline import (
    compile_current_paper,
    plan_narrative_and_claims,
    refine_current_paper,
    record_current_validation_report,
    review_current_paper,
    write_figure_placement_review,
)
from paperorchestra.manuscript.source_obligations import write_source_obligations
from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.runtime.providers import BaseProvider
from ..quality.loop import CITATION_SUPPORT_REVIEW_REFRESH_CODES, REVIEW_REFRESH_CODES
from .artifacts import _refresh_citation_integrity_for_current_manuscript, _try_rebuild_bib_for_citation_quality
from .repair import repair_citation_claims
from .semantic_recheck import _citation_repair_failure_payload
from .state import _artifact_sha, guarded_replace_manuscript_text


@dataclass(frozen=True)
class QaLoopActionDispatchContext:
    cwd: str | Path | None
    provider: BaseProvider
    runtime_mode: str
    require_compile: bool
    quality_mode: str
    citation_evidence_mode: str
    citation_provider: BaseProvider | None
    paper_path: Path | None
    original_paper: str | None


@dataclass(frozen=True)
class QaLoopActionDispatchResult:
    citation_candidate_applied: bool
    citation_candidate_path: str | None


def _preserve_citation_candidate_for_approval(
    cwd: str | Path | None,
    candidate_path: str | Path | None,
) -> str | None:
    if not candidate_path:
        return None
    source = Path(candidate_path).resolve()
    if not source.exists() or not source.is_file():
        return str(source)
    digest = _artifact_sha(source)
    if not digest:
        return str(source)
    short = digest.split(":", 1)[-1][:16]
    preserved = artifact_path(cwd, f"paper.citation-repair.approval-{short}.candidate.tex")
    if not preserved.exists() or _artifact_sha(preserved) != digest:
        preserved.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return str(preserved)


def dispatch_qa_loop_actions(
    actions: list[dict[str, Any]],
    execution: dict[str, Any],
    context: QaLoopActionDispatchContext,
) -> QaLoopActionDispatchResult:
    citation_candidate_applied = False
    citation_candidate_path: str | None = None
    for action in actions:
        code = str(action.get("code"))
        if code in {
            "narrative_plan_missing",
            "claim_map_missing",
            "citation_placement_plan_missing",
            "narrative_plan_stale",
            "claim_map_stale",
            "citation_placement_plan_stale",
        }:
            paths = plan_narrative_and_claims(context.cwd, provider=None, runtime_mode=context.runtime_mode)
            execution["actions_attempted"].append(
                {
                    "code": code,
                    "handler": "plan_narrative",
                    "paths": {key: str(path) for key, path in paths.items()},
                }
            )
        elif code in {"validation_report_missing", "validation_report_stale"}:
            validation_path, validation_payload = record_current_validation_report(
                context.cwd,
                name="validation.qa-loop-step.precondition.json",
            )
            execution["actions_attempted"].append(
                {
                    "code": code,
                    "handler": "validate_current",
                    "path": str(validation_path),
                    "ok": validation_payload.get("ok"),
                }
            )
        elif code in {"figure_placement_review_missing", "figure_placement_review_stale"}:
            figure_path, figure_payload = write_figure_placement_review(context.cwd)
            execution["actions_attempted"].append(
                {
                    "code": code,
                    "handler": "review_figure_placement",
                    "path": str(figure_path),
                    "warning_count": (figure_payload.get("summary") or {}).get("warning_count")
                    if isinstance(figure_payload, dict)
                    else None,
                }
            )
        elif code in CITATION_SUPPORT_REVIEW_REFRESH_CODES | {"citation_support_evidence_research_needed"}:
            review_path = write_citation_support_review(
                context.cwd,
                provider=context.citation_provider,
                evidence_mode=context.citation_evidence_mode,
            )
            execution["actions_attempted"].append(
                {"code": code, "handler": "critique_citations", "path": str(review_path)}
            )
        elif code in {
            "critical_unknown_reference",
            "critical_missing_bib_entry",
            "critical_unsupported_citation",
            "critical_citation_support_missing",
            "critical_weak_reference_identity",
        }:
            bibtex_rebuild = (
                _try_rebuild_bib_for_citation_quality(context.cwd)
                if code == "critical_weak_reference_identity"
                else None
            )
            review_path = write_citation_support_review(
                context.cwd,
                provider=context.citation_provider,
                evidence_mode=context.citation_evidence_mode,
            )
            refreshed = _refresh_citation_integrity_for_current_manuscript(
                context.cwd,
                quality_mode=context.quality_mode,
            )
            attempted = {
                "code": code,
                "handler": "refresh_citation_quality",
                "citation_support_review": str(review_path),
                "citation_integrity": refreshed,
            }
            if bibtex_rebuild is not None:
                attempted["bibtex_rebuild"] = bibtex_rebuild
            execution["actions_attempted"].append(attempted)
        elif code in {
            "rendered_reference_audit_missing",
            "rendered_reference_audit_stale",
            "citation_intent_plan_missing",
            "citation_intent_plan_stale",
            "citation_source_match_missing",
            "citation_source_match_stale",
            "citation_integrity_missing",
            "citation_integrity_stale",
            "citation_critic_missing",
            "citation_critic_stale",
        }:
            refreshed = _refresh_citation_integrity_for_current_manuscript(
                context.cwd,
                quality_mode=context.quality_mode,
            )
            execution["actions_attempted"].append(
                {"code": code, "handler": "refresh_citation_integrity", "artifacts": refreshed}
            )
        elif code in REVIEW_REFRESH_CODES:
            path = review_current_paper(context.cwd, context.provider, runtime_mode=context.runtime_mode)
            execution["actions_attempted"].append({"code": code, "handler": "review", "path": str(path)})
        elif code in {
            "compile_report_missing",
            "compile_report_stale",
            "compile_report_legacy_untrusted",
            "compile_pdf_missing",
            "compile_pdf_stale",
            "compile_not_clean",
        }:
            try:
                pdf_path = compile_current_paper(context.cwd)
                execution["actions_attempted"].append(
                    {"code": code, "handler": "compile", "pdf": str(pdf_path), "ok": True}
                )
            except Exception as exc:
                execution["actions_attempted"].append(
                    {"code": code, "handler": "compile", "ok": False, "error": str(exc)}
                )
                break
        elif code in {"section_review_missing", "section_review_stale", "section_review_legacy_untrusted"}:
            path = write_section_review(context.cwd)
            execution["actions_attempted"].append({"code": code, "handler": "critique_sections", "path": str(path)})
        elif code in {"source_obligations_missing", "source_obligations_stale"}:
            path = write_source_obligations(context.cwd)
            execution["actions_attempted"].append(
                {"code": code, "handler": "build_source_obligations", "path": str(path)}
            )
        elif code in {
            "review_score_below_threshold",
            "section_quality_below_threshold",
            "source_material_coverage_insufficient",
        }:
            state = load_session(context.cwd)
            if not state.artifacts.latest_review_json:
                review_path = review_current_paper(context.cwd, context.provider, runtime_mode=context.runtime_mode)
                execution["actions_attempted"].append(
                    {"code": code, "handler": "review", "path": str(review_path), "reason": "required_before_refine"}
                )
            refine_result = refine_current_paper(
                context.cwd,
                context.provider,
                iterations=1,
                require_compile_for_accept=context.require_compile,
                runtime_mode=context.runtime_mode,
                claim_safe=context.quality_mode == "claim_safe",
            )
            section_path = write_section_review(context.cwd)
            execution["actions_attempted"].append(
                {"code": code, "handler": "refine", "result": refine_result, "section_review": str(section_path)}
            )
            if any(not item.get("accepted", False) for item in refine_result):
                break
        elif code in {
            "citation_support_critic_failed",
            "citation_density_policy_failed",
            "citation_coverage_insufficient",
            "high_risk_uncited_claim",
        }:
            repair = repair_citation_claims(
                context.cwd,
                context.provider,
                runtime_mode=context.runtime_mode,
                require_compile=context.require_compile,
                commit=False,
            )
            if not repair.get("accepted"):
                failure = _citation_repair_failure_payload(code, repair)
                execution.setdefault("repair_failures", []).append(failure)
                execution["actionable_failure"] = {
                    "category": "citation_repair_failed",
                    "code": code,
                    "reason": failure["reason"],
                    "validation_failing_codes": failure["validation"]["failing_codes"],
                    "semantic_recheck_blockers": failure.get("semantic_recheck_blockers") or [],
                    "next_steps": failure["next_steps"],
                }
                execution["actions_attempted"].append(
                    {"code": code, "handler": "repair_citation_claims", "result": repair}
                )
                break
            if context.paper_path and repair.get("candidate_path"):
                preserved_candidate_path = _preserve_citation_candidate_for_approval(
                    context.cwd,
                    repair.get("candidate_path"),
                )
                if preserved_candidate_path:
                    repair = dict(repair)
                    repair.setdefault("raw_candidate_path", str(repair.get("candidate_path")))
                    repair["candidate_path"] = preserved_candidate_path
                    repair["candidate_sha256"] = _artifact_sha(preserved_candidate_path)
                citation_candidate_path = str(repair["candidate_path"])
                guarded_replace_manuscript_text(
                    context.cwd,
                    context.paper_path,
                    Path(citation_candidate_path).read_text(encoding="utf-8"),
                    reason="qa_loop_citation_candidate_for_validation",
                    original_text=context.original_paper,
                )
                citation_candidate_applied = True
            execution["actions_attempted"].append({"code": code, "handler": "repair_citation_claims", "result": repair})
        else:
            execution["actions_skipped"].append({"code": code, "reason": "no_handler"})
    return QaLoopActionDispatchResult(
        citation_candidate_applied=citation_candidate_applied,
        citation_candidate_path=citation_candidate_path,
    )
