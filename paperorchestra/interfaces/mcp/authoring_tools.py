from __future__ import annotations

from pathlib import Path

from paperorchestra.core.session import load_session
from paperorchestra.engine.pipeline import run_pipeline
from paperorchestra.engine.research_prior_work_stage import import_prior_work, research_prior_work as generate_prior_work_seed
from paperorchestra.engine.review_stages import compile_current_paper, review_current_paper
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.feedback.human_needed import record_human_needed_answer
from paperorchestra.interfaces.exporting import export_current_artifacts
from paperorchestra.interfaces.mcp.common import JSON, default_cwd, ok, provider_from_args
from paperorchestra.manuscript.revisions import write_revision_suggestions
from paperorchestra.reviews.citation_model_writer import write_citation_support_review
from paperorchestra.reviews.section_review import write_section_review
from paperorchestra.runtime.provider_registry import get_citation_support_provider


def tool_research_prior_work(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    return ok(
        generate_prior_work_seed(
            cwd,
            provider_from_args(arguments),
            output=arguments.get("output"),
            paper=arguments.get("paper"),
            artifact_repo=arguments.get("artifact_repo"),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
            source=arguments.get("source", "codex_web_seed"),
            import_seed=bool(arguments.get("import_seed", False)),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_import_prior_work(arguments: JSON) -> JSON:
    return ok(
        import_prior_work(
            default_cwd(arguments),
            seed_file=arguments["seed_file"],
            source=arguments.get("source", "manual_seed"),
            require_complete_metadata=bool(arguments.get("require_complete_metadata", False)),
        )
    )


def tool_write_sections(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    return ok(
        {
            "path": str(
                write_sections(
                    cwd,
                    provider_from_args(arguments),
                    runtime_mode=arguments.get("runtime_mode", "compatibility"),
                    only_sections=arguments.get("only_sections"),
                    output_path=arguments.get("output_path"),
                    claim_safe=bool(arguments.get("claim_safe", False)),
                )
            )
        }
    )


def tool_critique(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    provider = provider_from_args(arguments)
    state = load_session(cwd)
    output_dir = Path(arguments["output_dir"]).resolve() if arguments.get("output_dir") else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_current_paper(cwd, provider, runtime_mode=arguments.get("runtime_mode", "compatibility"))
    section_path = write_section_review(cwd, output_dir / "section_review.json")
    evidence_mode = arguments.get("citation_evidence_mode") or "heuristic"
    citation_provider = get_citation_support_provider(arguments.get("provider", "mock"), command=arguments.get("provider_command"), evidence_mode=evidence_mode)
    citation_path = write_citation_support_review(cwd, output_dir / "citation_support_review.json", provider=citation_provider, evidence_mode=evidence_mode)
    suggestions_path = write_revision_suggestions(
        arguments.get("source_paper") or state.artifacts.paper_full_tex,
        review_path,
        output_dir / "revision_suggestions.json",
        section_review_json=section_path,
        citation_review_json=citation_path,
    )
    return ok({"review": str(review_path), "section_review": str(section_path), "citation_support_review": str(citation_path), "revision_suggestions": str(suggestions_path)})


def tool_compile_current_paper(arguments: JSON) -> JSON:
    return ok({"path": str(compile_current_paper(default_cwd(arguments)))})


def tool_answer_human_needed(arguments: JSON) -> JSON:
    provider = provider_from_args(arguments) if arguments.get("apply") else None
    payload = record_human_needed_answer(
        default_cwd(arguments),
        str(arguments.get("answer") or ""),
        packet_path=arguments.get("packet_path"),
        review_scope=arguments.get("review_scope"),
        intent=arguments.get("intent"),
        action_id=arguments.get("action_id"),
        output_answer=arguments.get("output_answer"),
        output_feedback=arguments.get("output_feedback"),
        redacted_answer_only=bool(arguments.get("redacted_answer_only", False)),
        apply=bool(arguments.get("apply", False)),
        imported_feedback_output=arguments.get("imported_feedback_output"),
        provider=provider,
        max_supervised_iterations=int(arguments.get("max_supervised_iterations", 1)),
        require_compile=bool(arguments.get("require_compile", False)),
        quality_mode=arguments.get("quality_mode", "claim_safe"),
        max_iterations=int(arguments.get("max_iterations", 10)),
        require_live_verification=bool(arguments.get("require_live_verification", False)),
        accept_mixed_provenance=bool(arguments.get("accept_mixed_provenance", False)),
        runtime_mode=arguments.get("runtime_mode", "compatibility"),
        citation_evidence_mode=arguments.get("citation_evidence_mode", "web"),
        citation_provider_name=arguments.get("citation_provider"),
        citation_provider_command=arguments.get("citation_provider_command"),
    )
    return ok(payload)


def tool_export_current(arguments: JSON) -> JSON:
    return ok(export_current_artifacts(default_cwd(arguments), arguments["output"], include_all_artifacts=bool(arguments.get("include_all_artifacts", False))))


def tool_run_pipeline(arguments: JSON) -> JSON:
    cwd = default_cwd(arguments)
    return ok(
        run_pipeline(
            cwd,
            provider=provider_from_args(arguments),
            discovery_mode=arguments.get("discovery_mode", "model"),
            verify_mode=arguments.get("verify_mode", "live"),
            verify_error_policy=arguments.get("verify_error_policy", "skip"),
            verify_fallback_mode=arguments.get("verify_fallback_mode", "none"),
            require_live_verification=bool(arguments.get("require_live_verification", False)),
            refine_iterations=int(arguments.get("refine_iterations", 1)),
            compile_paper=bool(arguments.get("compile_paper", False)),
            runtime_mode=arguments.get("runtime_mode", "compatibility"),
        )
    )
