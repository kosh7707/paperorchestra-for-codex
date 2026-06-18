from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paperorchestra.core.session import load_session
from paperorchestra.engine.pipeline import (
    import_prior_work,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    run_pipeline,
    write_sections,
)
from paperorchestra.interfaces.cli_commands.common import provider_from_args, strict_omx_env
from paperorchestra.manuscript.revisions import write_revision_suggestions
from paperorchestra.reviews.critic_trust import build_critic_trust_card, require_live_critic_trust
from paperorchestra.reviews.critics import write_citation_support_review, write_section_review
from paperorchestra.runtime.providers import get_citation_support_provider


def handle_research_prior_work(cwd: Path, args: argparse.Namespace) -> int:
    provider = provider_from_args(args)
    with strict_omx_env(args.strict_omx_native):
        payload = generate_prior_work_seed(
            cwd,
            provider,
            output=args.output,
            paper=args.paper,
            artifact_repo=args.artifact_repo,
            runtime_mode=args.runtime_mode,
            source=args.source,
            import_seed=args.import_seed,
            require_complete_metadata=args.require_complete_metadata,
        )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def handle_import_prior_work(cwd: Path, args: argparse.Namespace) -> int:
    payload = import_prior_work(cwd, seed_file=args.seed_file, source=args.source, require_complete_metadata=args.require_complete_metadata)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def handle_write_sections(cwd: Path, args: argparse.Namespace) -> int:
    provider = provider_from_args(args)
    with strict_omx_env(args.strict_omx_native):
        path = write_sections(
            cwd,
            provider,
            runtime_mode=args.runtime_mode,
            only_sections=args.only_sections,
            output_path=args.output_tex,
            claim_safe=args.claim_safe,
        )
    print(path)
    return 0


def handle_critique(cwd: Path, args: argparse.Namespace) -> int:
    trust_card = build_critic_trust_card(
        provider_name=args.provider,
        provider_command=args.provider_command,
        citation_evidence_mode=args.citation_evidence_mode,
        claim_safe=args.claim_safe,
    )
    if args.live:
        require_live_critic_trust(trust_card)
    provider = provider_from_args(args)
    state = load_session(cwd)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with strict_omx_env(args.strict_omx_native):
        review_path = review_current_paper(cwd, provider, runtime_mode=args.runtime_mode)
    section_path = write_section_review(cwd, output_dir / "section_review.json")
    citation_provider = get_citation_support_provider(args.provider, command=args.provider_command, evidence_mode=args.citation_evidence_mode)
    citation_path = write_citation_support_review(
        cwd,
        output_dir / "citation_support_review.json",
        provider=citation_provider,
        evidence_mode=args.citation_evidence_mode,
        progress_stream=sys.stderr if args.citation_evidence_mode in {"model", "web"} else None,
    )
    source_paper = args.source_paper or state.artifacts.paper_full_tex
    suggestions_path = write_revision_suggestions(
        source_paper,
        review_path,
        output_dir / "revision_suggestions.json",
        section_review_json=section_path,
        citation_review_json=citation_path,
    )
    print(
        json.dumps(
            {
                "critic_trust": trust_card,
                "review": str(review_path),
                "section_review": str(section_path),
                "citation_support_review": str(citation_path),
                "revision_suggestions": str(suggestions_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def handle_run(cwd: Path, args: argparse.Namespace) -> int:
    provider = provider_from_args(args)
    with strict_omx_env(args.strict_omx_native):
        result = run_pipeline(
            cwd,
            provider=provider,
            discovery_mode=args.discovery_mode,
            verify_mode=args.verify_mode,
            verify_error_policy=args.verify_error_policy,
            verify_fallback_mode=args.verify_fallback_mode,
            require_live_verification=args.require_live_verification,
            refine_iterations=args.refine_iterations,
            compile_paper=args.compile,
            runtime_mode=args.runtime_mode,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("status") == "blocked" else 0
