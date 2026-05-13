from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .compile_env import inspect_compile_environment
from .cost import estimate_run_cost
from .citation_integrity import (
    write_citation_integrity_audit,
    write_citation_integrity_critic,
    write_rendered_reference_audit,
)
from .critics import write_citation_support_review, write_section_review
from .doctor import build_doctor_report, build_session_recovery_hint
from .environment import build_environment_inventory
from .fidelity import write_reproducibility_audit
from .io_utils import write_json
from .eval import (
    write_review_gate_comparison,
    write_reference_case_partition_scaffold,
    write_reference_case_partitioned_citation_coverage,
    write_generated_citation_titles,
    write_citation_partition_request,
    write_partitioned_citation_coverage,
    write_reference_benchmark_case,
    write_reference_comparison,
    write_session_eval_summary,
)
from .intake import (
    answer_intake_question,
    approve_intake_direction,
    finalize_intake,
    get_intake_review,
    get_intake_status,
    research_prior_work,
    start_intake,
)
from .jobs import cancel_job, get_job_status, list_jobs, start_run_job, tail_job_log
from .models import InputBundle
from .omx_bridge import cleanup_omx_tmp
from .omx_diagnostics import export_omx_evidence, write_omx_review_handoff
from .operator_feedback import apply_operator_feedback, build_operator_review_packet, import_operator_feedback
from .orchestra_evidence import write_orchestrator_evidence_bundle
from .orchestra_scorecard import render_scorecard_summary
from .orchestrator import inspect_state as orchestrator_inspect_state, run_until_blocked as orchestrator_run_until_blocked
from .quality_loop import write_quality_eval, write_quality_loop_plan
from .quality_gate import write_quality_gate
from .ralph_bridge import (
    build_ralph_start_payload,
    launch_omx_ralph,
    repair_citation_claims,
    run_qa_loop_step,
    write_qa_loop_brief,
)
from .pipeline import (
    build_bib,
    compile_current_paper,
    discover_papers,
    generate_outline,
    generate_plots,
    import_prior_work,
    plan_narrative_and_claims,
    record_compile_environment_report,
    record_current_validation_report,
    refine_current_paper,
    research_prior_work as generate_prior_work_seed,
    review_current_paper,
    record_fidelity_report,
    run_pipeline,
    verify_papers,
    write_figure_placement_review,
    write_intro_related,
    write_sections,
)
from .providers import get_citation_support_provider, get_provider
from .revisions import write_revision_suggestions
from .session import artifact_path, create_session, get_current_session_id, load_session, run_dir
from .source_obligations import write_source_obligations
from .teach import prepare_teach_bundle


def _common_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", default="shell", choices=["shell", "mock"])
    parser.add_argument("--provider-command", default=None)


def _citation_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--citation-provider", default=None, choices=["shell", "mock"])
    parser.add_argument("--citation-provider-command", default=None)


def _runtime_mode_args(parser: argparse.ArgumentParser, *, strict_flag: bool = False) -> None:
    parser.add_argument("--runtime-mode", default="compatibility", choices=["compatibility", "omx_native"])
    if strict_flag:
        parser.add_argument("--strict-omx-native", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperorchestra", description="PaperOrchestra operator/debug CLI for the PaperOrchestra-on-OMX core")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize a PaperOrchestra session")
    init_parser.add_argument("--idea", required=True)
    init_parser.add_argument("--experimental-log", required=True)
    init_parser.add_argument("--template", required=True)
    init_parser.add_argument("--guidelines", required=True)
    init_parser.add_argument("--figures-dir")
    init_parser.add_argument("--cutoff-date")
    init_parser.add_argument("--venue")
    init_parser.add_argument("--page-limit", type=int)
    init_parser.add_argument("--allow-outside-workspace", action="store_true", help="Allow init to snapshot inputs from outside the current workspace.")

    status_parser = sub.add_parser("status", help="Show current session state")
    status_parser.add_argument("--json", action="store_true")
    status_parser.add_argument("--summary", action="store_true", help="Print a compact first-user session summary")

    inspect_state_parser = sub.add_parser("inspect-state", help="Inspect the v1 OrchestraState without running live work")
    inspect_state_parser.add_argument("--material", help="Optional material directory/file to inspect")
    inspect_state_parser.add_argument("--json", action="store_true")

    orchestrate_parser = sub.add_parser("orchestrate", help="Run the v1 orchestrator until the next bounded action/block")
    orchestrate_parser.add_argument("--material", help="Optional material directory/file to inspect")
    orchestrate_parser.add_argument("--write-evidence", action="store_true", help="Persist a public-safe orchestrator evidence bundle")
    orchestrate_parser.add_argument("--evidence-output", help="Workspace-contained evidence bundle directory")
    orchestrate_parser.add_argument("--json", action="store_true")

    continue_project_parser = sub.add_parser("continue-project", help="Continue the v1 orchestrator from current state without live work")
    continue_project_parser.add_argument("--json", action="store_true")

    answer_human_needed_parser = sub.add_parser("answer-human-needed", help="Record a bounded answer for a human_needed stop (skeleton)")
    answer_human_needed_parser.add_argument("--answer", required=True)
    answer_human_needed_parser.add_argument("--json", action="store_true")

    export_parser = sub.add_parser("export-artifacts", help="Copy the current session's main outputs to an easy-to-share directory")
    export_parser.add_argument("--output", required=True, help="Destination directory for exported outputs")
    export_parser.add_argument("--include-all-artifacts", action="store_true", help="Also copy the complete session artifacts/ directory")
    export_parser.add_argument("--json", action="store_true", help="Print machine-readable export details")

    export_current_parser = sub.add_parser("export-current", help="Alias for export-artifacts")
    export_current_parser.add_argument("--output", required=True, help="Destination directory for exported outputs")
    export_current_parser.add_argument("--include-all-artifacts", action="store_true", help="Also copy the complete session artifacts/ directory")
    export_current_parser.add_argument("--json", action="store_true", help="Print machine-readable export details")

    quickstart_parser = sub.add_parser("quickstart", help="Print a short operator guide for common PaperOrchestra workflows")
    quickstart_parser.add_argument("--scenario", default="new-paper", choices=["new-paper", "testset", "curated-prior-work", "environment"])

    teach_parser = sub.add_parser("teach", help="Prepare PaperOrchestra inputs from an existing manuscript/artifact repo")
    teach_parser.add_argument("--paper", required=True)
    teach_parser.add_argument("--pdf")
    teach_parser.add_argument("--artifact-repo")
    teach_parser.add_argument("--figures-dir")
    teach_parser.add_argument("--output-dir")
    teach_parser.add_argument("--no-init-session", action="store_true")
    teach_parser.add_argument("--allow-outside-workspace", action="store_true", help="Allow teach-mode inputs and outputs outside the current workspace.")

    intake_start_parser = sub.add_parser("intake-start", help="Start a guided intake session")
    intake_start_parser.add_argument("--seed-answers")

    intake_status_parser = sub.add_parser("intake-status", help="Show guided intake status")
    intake_status_parser.add_argument("--intake-id")

    intake_review_parser = sub.add_parser("intake-review", help="Show the review packet for a guided intake")
    intake_review_parser.add_argument("--intake-id")

    intake_answer_parser = sub.add_parser("intake-answer", help="Answer one or more guided intake questions")
    intake_answer_parser.add_argument("--intake-id")
    intake_answer_parser.add_argument("--key")
    intake_answer_parser.add_argument("--answer")
    intake_answer_parser.add_argument("--answers-json")

    intake_research_parser = sub.add_parser("intake-research", help="Enrich the current intake with prior-work search")
    intake_research_parser.add_argument("--intake-id")
    intake_research_parser.add_argument("--mode", default="live", choices=["live", "mock"])
    intake_research_parser.add_argument("--max-per-seed", type=int, default=2)
    intake_research_parser.add_argument("--allow-outside-workspace", action="store_true")

    intake_finalize_parser = sub.add_parser("intake-finalize", help="Generate input artifacts from the current guided intake")
    intake_finalize_parser.add_argument("--intake-id")
    intake_finalize_parser.add_argument("--output-dir")
    intake_finalize_parser.add_argument("--template-path")
    intake_finalize_parser.add_argument("--figures-dir")
    intake_finalize_parser.add_argument("--no-init-session", action="store_true")
    intake_finalize_parser.add_argument("--allow-overwrite", action="store_true")
    intake_finalize_parser.add_argument("--allow-outside-workspace", action="store_true", help="Allow finalize output/template/figure paths outside the current workspace.")
    intake_finalize_parser.add_argument("--story-candidate-id")
    intake_finalize_parser.add_argument("--claim-candidate-ids")

    intake_approve_parser = sub.add_parser("intake-approve", help="Approve a story/claim direction and finalize the intake")
    intake_approve_parser.add_argument("--intake-id")
    intake_approve_parser.add_argument("--story-candidate-id", required=True)
    intake_approve_parser.add_argument("--claim-candidate-ids", required=True)
    intake_approve_parser.add_argument("--output-dir")
    intake_approve_parser.add_argument("--template-path")
    intake_approve_parser.add_argument("--figures-dir")
    intake_approve_parser.add_argument("--no-init-session", action="store_true")
    intake_approve_parser.add_argument("--allow-overwrite", action="store_true")
    intake_approve_parser.add_argument("--allow-outside-workspace", action="store_true", help="Allow approve/finalize output/template/figure paths outside the current workspace.")

    jobs_start_parser = sub.add_parser("job-start-run", help="Start a background pipeline run")
    jobs_start_parser.add_argument("--discovery-mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    jobs_start_parser.add_argument("--verify-mode", default="live", choices=["live", "mock"])
    jobs_start_parser.add_argument("--verify-error-policy", default="skip", choices=["skip", "fail"])
    jobs_start_parser.add_argument("--verify-fallback-mode", default="none", choices=["none", "mock"], help="If live verification fails, optionally fall back to mock verification instead of aborting.")
    jobs_start_parser.add_argument("--require-live-verification", action="store_true", help="Treat skipped live citation verification as a blocking reproducibility failure.")
    jobs_start_parser.add_argument("--refine-iterations", type=int, default=1)
    jobs_start_parser.add_argument("--compile", action="store_true")
    _runtime_mode_args(jobs_start_parser, strict_flag=True)
    _common_provider_args(jobs_start_parser)

    jobs_list_parser = sub.add_parser("jobs-list", help="List recent background jobs")
    jobs_list_parser.add_argument("--limit", type=int, default=20)

    job_status_parser = sub.add_parser("job-status", help="Show background job status")
    job_status_parser.add_argument("--job-id", required=True)
    run_status_parser = sub.add_parser("run-status", help="Alias for job-status")
    run_status_parser.add_argument("--job-id", required=True)

    job_tail_parser = sub.add_parser("job-tail-log", help="Tail the log of a background job")
    job_tail_parser.add_argument("--job-id", required=True)
    job_tail_parser.add_argument("--lines", type=int, default=40)
    run_tail_parser = sub.add_parser("run-tail-log", help="Alias for job-tail-log")
    run_tail_parser.add_argument("--job-id", required=True)
    run_tail_parser.add_argument("--lines", type=int, default=40)

    job_cancel_parser = sub.add_parser("job-cancel", help="Cancel a running background job")
    job_cancel_parser.add_argument("--job-id", required=True)

    outline_parser = sub.add_parser("outline", help="Generate outline.json")
    _runtime_mode_args(outline_parser, strict_flag=True)
    _common_provider_args(outline_parser)

    plots_parser = sub.add_parser("generate-plots", help="Generate plot manifest artifacts")
    _runtime_mode_args(plots_parser, strict_flag=True)
    _common_provider_args(plots_parser)

    discover_parser = sub.add_parser("discover-papers", help="Generate candidate_papers.json")
    discover_parser.add_argument("--mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    _runtime_mode_args(discover_parser, strict_flag=True)
    _common_provider_args(discover_parser)

    import_prior_parser = sub.add_parser("import-prior-work", help="Import curated prior-work seeds into citation artifacts")
    import_prior_parser.add_argument("--seed-file", required=True)
    import_prior_parser.add_argument("--source", default="manual_seed")
    import_prior_parser.add_argument(
        "--require-complete-metadata",
        action="store_true",
        help="Reject seed entries without title, author/organization, and concrete year before building claim-safe references.",
    )

    narrative_parser = sub.add_parser("plan-narrative", help="Write narrative, claim-map, and citation-placement planning artifacts")
    _runtime_mode_args(narrative_parser, strict_flag=True)
    _common_provider_args(narrative_parser)

    research_prior_parser = sub.add_parser("research-prior-work", help="Generate a curated prior-work seed JSON from current materials")
    research_prior_parser.add_argument("--output")
    research_prior_parser.add_argument("--paper")
    research_prior_parser.add_argument("--artifact-repo")
    _runtime_mode_args(research_prior_parser, strict_flag=True)
    research_prior_parser.add_argument("--source", default="codex_web_seed")
    research_prior_parser.add_argument("--import", dest="import_seed", action="store_true")
    research_prior_parser.add_argument(
        "--require-complete-metadata",
        action="store_true",
        help="When used with --import, reject seed entries without title, author/organization, and concrete year.",
    )
    _common_provider_args(research_prior_parser)

    verify_parser = sub.add_parser("verify-papers", help="Verify candidate papers with Semantic Scholar")
    verify_parser.add_argument("--min-ratio", type=float, default=70.0)
    verify_parser.add_argument("--mode", default="live", choices=["live", "mock"])
    verify_parser.add_argument("--on-error", default="skip", choices=["skip", "fail"])

    sub.add_parser("build-bib", help="Generate references.bib from verified citation registry")

    intro_parser = sub.add_parser("write-intro-related", help="Draft Introduction and Related Work")
    _runtime_mode_args(intro_parser, strict_flag=True)
    intro_parser.add_argument("--claim-safe", action="store_true", help="Fail closed on claim-safe citation/source prompt contract violations.")
    intro_parser.add_argument(
        "--allow-recoverable-contract-issues",
        action="store_true",
        help=(
            "Persist a draft when only recoverable citation-coverage blockers remain, "
            "so supervised QA/operator loops can repair it instead of aborting early."
        ),
    )
    _common_provider_args(intro_parser)

    sections_parser = sub.add_parser("write-sections", help="Draft the full paper")
    _runtime_mode_args(sections_parser, strict_flag=True)
    sections_parser.add_argument("--only-sections", help="Comma-separated section titles to rewrite while preserving all other existing sections.")
    sections_parser.add_argument("--output-tex", help="Write the resulting manuscript to this explicit path instead of the default paper.full.tex artifact.")
    sections_parser.add_argument("--claim-safe", action="store_true", help="Fail closed on claim-safe citation/source prompt contract violations.")
    _common_provider_args(sections_parser)

    sub.add_parser("compile", help="Compile the current paper.full.tex")
    sub.add_parser("check-compile-env", help="Inspect and record the compile environment readiness")
    sub.add_parser("bootstrap-compile-env", help="Print compile environment remediation commands and generated bootstrap script path")
    environment_parser = sub.add_parser("environment", help="Show the canonical environment-variable inventory, docs, and readiness profiles")
    environment_parser.add_argument("--json", action="store_true", help="Print the full machine-readable inventory (default for compatibility)")
    environment_parser.add_argument("--summary", action="store_true", help="Print a compact human-readable readiness summary")
    doctor_parser = sub.add_parser("doctor", help="Run a pre-flight environment check for live PaperOrchestra runs")
    doctor_parser.add_argument("--omx-deep", action="store_true", help="Include bounded OMX state/trace/Ralph/sparkshell/team probes")
    doctor_parser.add_argument("--omx-timeout", type=float, default=10.0, help="Timeout seconds for each bounded --omx-deep probe")
    omx_evidence_parser = sub.add_parser("export-omx-evidence", help="Export OMX trace/state/status summaries to an evidence directory")
    omx_evidence_parser.add_argument("--output", required=True)
    omx_evidence_parser.add_argument("--timeout", type=float, default=10.0)
    omx_review_handoff_parser = sub.add_parser("omx-review-handoff", help="Write a safe manual handoff for OMX Critic/team/ultrawork review")
    omx_review_handoff_parser.add_argument("--output")
    cleanup_tmp_parser = sub.add_parser("cleanup-tmp", help="Remove temporary OMX execution artifacts")
    cleanup_tmp_parser.add_argument("--max-age-seconds", type=float, default=0.0)

    review_parser = sub.add_parser("review", help="Review the current paper")
    review_parser.add_argument("--output", help="Review artifact name/path (default: review.latest.json)")
    _runtime_mode_args(review_parser, strict_flag=True)
    _common_provider_args(review_parser)
    section_review_parser = sub.add_parser("review-sections", help="Run a section-level critic over the current manuscript")
    section_review_parser.add_argument("--output")
    citation_review_parser = sub.add_parser("review-citations", help="Run a citation-support critic over cited claims")
    citation_review_parser.add_argument("--output")
    citation_review_parser.add_argument(
        "--evidence-mode",
        default="heuristic",
        choices=["heuristic", "model", "web"],
        help="Use heuristic metadata checks, a model critic, or a web-search-capable model critic for cited-sentence support.",
    )
    _common_provider_args(citation_review_parser)
    rendered_reference_parser = sub.add_parser("audit-rendered-references", help="Audit the rendered bibliography denominator and visible BibTeX metadata")
    rendered_reference_parser.add_argument("--output")
    rendered_reference_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"])
    citation_integrity_parser = sub.add_parser("audit-citation-integrity", help="Write citation intent/source-match/integrity artifacts for claim-safe quality gates")
    citation_integrity_parser.add_argument("--output")
    citation_integrity_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"])
    citation_critic_parser = sub.add_parser(
        "audit-citation-integrity-critic",
        help="Write the deterministic citation integrity critic artifact for claim-safe quality gates",
    )
    citation_critic_parser.add_argument("--output")
    citation_critic_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"])
    figure_review_parser = sub.add_parser("review-figure-placement", help="Build a figure-placement review packet for the current manuscript")
    figure_review_parser.add_argument("--output")
    validate_current_parser = sub.add_parser("validate-current", help="Record validation issues for the current manuscript without rewriting it")
    validate_current_parser.add_argument("--output")
    validate_claim_safe_parser = sub.add_parser(
        "validate-claim-safe-current",
        help="Record structural validation plus claim-safe quality-loop blockers for the current manuscript",
    )
    validate_claim_safe_parser.add_argument("--output")
    validate_claim_safe_parser.add_argument("--max-iterations", type=int, default=10)
    validate_claim_safe_parser.add_argument("--require-live-verification", action="store_true")
    source_obligations_parser = sub.add_parser("build-source-obligations", help="Build source_obligations.json from the current session input packet")
    source_obligations_parser.add_argument("--output")

    sub.add_parser("audit-fidelity", help="Audit the current implementation/session against paper-derived fidelity checks")
    reproducibility_parser = sub.add_parser("audit-reproducibility", help="Classify whether the current run supports reproducibility/fidelity claims")
    reproducibility_parser.add_argument("--output")
    reproducibility_parser.add_argument("--require-live-verification", action="store_true", help="Treat skipped live citation verification as a blocking reproducibility failure.")
    quality_eval_parser = sub.add_parser("quality-eval", help="Write the tiered quality-eval diagnostic snapshot for the current session")
    quality_eval_parser.add_argument("--output")
    quality_eval_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"], help="Evaluation mode controlling claim-safety and score thresholds.")
    quality_eval_parser.add_argument("--max-iterations", type=int, default=10, help="Iteration budget recorded in cross-iteration metadata.")
    quality_eval_parser.add_argument("--require-live-verification", action="store_true", help="Pass through to reproducibility audit for claim-safe runs.")
    quality_eval_parser.add_argument("--record-history", action="store_true", help="Append this diagnostic-only quality evaluation to qa-loop-history.jsonl.")
    quality_gate_parser = sub.add_parser("quality-gate", help="Run the strict draft-quality gate and write quality-gate.report.json")
    quality_gate_parser.add_argument("--output")
    quality_gate_parser.add_argument("--plan-output")
    quality_gate_parser.add_argument("--profile", default="auto", choices=["auto", "mock", "ralph", "claim_safe"], help="Gate strictness profile; auto uses mock for mock provenance, claim_safe for claim-safe evals, otherwise ralph.")
    quality_gate_parser.add_argument("--quality-mode", default="draft", choices=["draft", "ralph", "claim_safe"], help="Evaluation mode used to build the underlying quality-eval and repair plan.")
    quality_gate_parser.add_argument("--max-iterations", type=int, default=10)
    quality_gate_parser.add_argument("--require-live-verification", action="store_true")
    quality_gate_parser.add_argument("--accept-mixed-provenance", action="store_true")
    quality_gate_parser.add_argument("--auto-refine", action="store_true", help="Attempt one bounded refinement pass when the gate blocks or is repairable.")
    quality_gate_parser.add_argument("--refine-iterations", type=int, default=1)
    quality_gate_parser.add_argument("--require-compile-for-accept", action="store_true")
    quality_gate_parser.add_argument("--no-fail-on-block", action="store_true", help="Always exit 0 after writing the report, even when the gate blocks.")
    _runtime_mode_args(quality_gate_parser, strict_flag=True)
    _common_provider_args(quality_gate_parser)
    qa_loop_parser = sub.add_parser("qa-loop-plan", help="Build a Ralph-friendly repair plan from tiered quality-eval and audit artifacts")
    qa_loop_parser.add_argument("--output")
    qa_loop_parser.add_argument("--quality-eval", help="Consume an existing quality-eval.json diagnostic snapshot instead of regenerating one.")
    qa_loop_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"], help="Evaluation mode controlling claim-safety and score thresholds.")
    qa_loop_parser.add_argument("--max-iterations", type=int, default=10, help="Iteration budget recorded in cross-iteration metadata.")
    qa_loop_parser.add_argument("--accept-mixed-provenance", action="store_true", help="Allow ready_for_human_finalization when provenance is mixed but explicitly accepted by the operator.")
    qa_loop_parser.add_argument("--require-live-verification", action="store_true", help="Pass through to reproducibility audit when planning claim-safe repairs.")
    qa_loop_alias_parser = sub.add_parser("qa-loop", help="Alias for qa-loop-plan; currently builds the repair plan without executing edits")
    qa_loop_alias_parser.add_argument("--output")
    qa_loop_alias_parser.add_argument("--quality-eval", help="Consume an existing quality-eval.json diagnostic snapshot instead of regenerating one.")
    qa_loop_alias_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"], help="Evaluation mode controlling claim-safety and score thresholds.")
    qa_loop_alias_parser.add_argument("--max-iterations", type=int, default=10, help="Iteration budget recorded in cross-iteration metadata.")
    qa_loop_alias_parser.add_argument("--accept-mixed-provenance", action="store_true", help="Allow ready_for_human_finalization when provenance is mixed but explicitly accepted by the operator.")
    qa_loop_alias_parser.add_argument("--require-live-verification", action="store_true", help="Pass through to reproducibility audit when planning claim-safe repairs.")
    qa_loop_brief_parser = sub.add_parser("qa-loop-brief", help="Write a Ralph-readable brief from the current quality loop state")
    qa_loop_brief_parser.add_argument("--output")
    qa_loop_brief_parser.add_argument("--quality-eval")
    qa_loop_brief_parser.add_argument("--qa-loop-plan")
    qa_loop_brief_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    qa_loop_brief_parser.add_argument("--max-iterations", type=int, default=10)
    qa_loop_brief_parser.add_argument("--accept-mixed-provenance", action="store_true")
    qa_loop_brief_parser.add_argument("--require-live-verification", action="store_true")
    repair_citations_parser = sub.add_parser("repair-citation-claims", help="Run a bounded citation-claim repair pass from citation-support critic issues")
    repair_citations_parser.add_argument("--citation-review")
    repair_citations_parser.add_argument("--require-compile", action="store_true")
    _runtime_mode_args(repair_citations_parser, strict_flag=True)
    _common_provider_args(repair_citations_parser)
    qa_loop_step_parser = sub.add_parser("qa-loop-step", help="Execute exactly one bounded QA-loop repair iteration")
    qa_loop_step_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    qa_loop_step_parser.add_argument("--max-iterations", type=int, default=10)
    qa_loop_step_parser.add_argument("--accept-mixed-provenance", action="store_true")
    qa_loop_step_parser.add_argument("--require-live-verification", action="store_true")
    qa_loop_step_parser.add_argument("--require-compile", action="store_true")
    qa_loop_step_parser.add_argument("--citation-evidence-mode", default="web", choices=["heuristic", "model", "web"])
    _runtime_mode_args(qa_loop_step_parser, strict_flag=True)
    _common_provider_args(qa_loop_step_parser)
    _citation_provider_args(qa_loop_step_parser)
    ralph_start_parser = sub.add_parser("ralph-start", help="Create or explicitly launch an OMX Ralph handoff for the current quality loop")
    ralph_start_parser.add_argument("--output")
    ralph_start_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    ralph_start_parser.add_argument("--max-iterations", type=int, default=10)
    ralph_start_parser.add_argument("--require-live-verification", action="store_true")
    ralph_start_parser.add_argument("--accept-mixed-provenance", action="store_true")
    ralph_start_parser.add_argument("--evidence-root")
    ralph_start_parser.add_argument("--dry-run", action="store_true")
    ralph_start_parser.add_argument("--launch", action="store_true")
    operator_packet_parser = sub.add_parser("build-operator-review-packet", help="Build a hash-bound packet for external OMX/Codex operator review after human_needed")
    operator_packet_parser.add_argument("--output")
    operator_packet_parser.add_argument("--require-pdf", action="store_true")
    operator_packet_parser.add_argument("--review-scope", choices=["pdf_and_tex", "tex_only"])
    operator_import_parser = sub.add_parser("import-operator-feedback", help="Validate/import external Codex-operator feedback against a review packet")
    operator_import_parser.add_argument("--packet", required=True)
    operator_import_parser.add_argument("--feedback", required=True)
    operator_import_parser.add_argument("--output")
    operator_apply_parser = sub.add_parser("apply-operator-feedback", help="Run one bounded candidate-first supervised feedback cycle")
    operator_apply_parser.add_argument("--imported-feedback", required=True)
    operator_apply_parser.add_argument("--max-supervised-iterations", type=int, default=1)
    operator_apply_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    operator_apply_parser.add_argument("--max-iterations", type=int, default=10)
    operator_apply_parser.add_argument("--require-live-verification", action="store_true")
    operator_apply_parser.add_argument("--accept-mixed-provenance", action="store_true")
    operator_apply_parser.add_argument("--require-compile", action="store_true")
    operator_apply_parser.add_argument("--citation-evidence-mode", default="web", choices=["heuristic", "model", "web"])
    _runtime_mode_args(operator_apply_parser, strict_flag=True)
    _common_provider_args(operator_apply_parser)
    _citation_provider_args(operator_apply_parser)
    estimate_parser = sub.add_parser("estimate-cost", help="Estimate model/search/compile calls for a prospective pipeline run")
    estimate_parser.add_argument("--discovery-mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    estimate_parser.add_argument("--refine-iterations", type=int, default=1)
    estimate_parser.add_argument("--compile", action="store_true")
    _runtime_mode_args(estimate_parser)
    benchmark_parser = sub.add_parser("build-reference-benchmark-case", help="Build a paper-derived benchmark/eval scaffold artifact from extracted reference materials")
    benchmark_parser.add_argument("--reference-dir", required=True)
    benchmark_parser.add_argument("--output")
    benchmark_parser.add_argument("--source-pdf")
    session_eval_parser = sub.add_parser("build-session-eval-summary", help="Summarize the current session into a benchmark/eval-friendly artifact")
    session_eval_parser.add_argument("--output")
    review_compare_parser = sub.add_parser("build-review-gate-comparison", help="Compare the current review artifact against the expected AgentReview-style surface")
    review_compare_parser.add_argument("--output")
    generated_titles_parser = sub.add_parser("build-generated-citation-titles", help="Extract the generated citation title set from the current paper and citation map")
    generated_titles_parser.add_argument("--output")
    compare_parser = sub.add_parser("compare-reference-case", help="Compare the current session against a reference benchmark case artifact")
    compare_parser.add_argument("--reference-case", required=True)
    compare_parser.add_argument("--output")
    partition_scaffold_parser = sub.add_parser("build-reference-case-partition-scaffold", help="Build a partition scaffold from a reference benchmark case")
    partition_scaffold_parser.add_argument("--reference-case", required=True)
    partition_scaffold_parser.add_argument("--output")
    partition_compare_case_parser = sub.add_parser("compare-reference-case-citation-coverage", help="Compare current generated citations against a reference-case partition scaffold")
    partition_compare_case_parser.add_argument("--reference-case", required=True)
    partition_compare_case_parser.add_argument("--output")
    partition_request_parser = sub.add_parser("build-citation-partition-request", help="Build a Citation F1 P0/P1 partition request artifact from paper text and references")
    partition_request_parser.add_argument("--paper-text-file", required=True)
    partition_request_parser.add_argument("--references-json", required=True)
    partition_request_parser.add_argument("--output")
    partition_compare_parser = sub.add_parser("compare-partitioned-citation-coverage", help="Compare generated citation titles against a partitioned reference list")
    partition_compare_parser.add_argument("--references-json", required=True)
    partition_compare_parser.add_argument("--partition-json", required=True)
    partition_compare_parser.add_argument("--generated-titles-json", required=True)
    partition_compare_parser.add_argument("--output")

    suggest_parser = sub.add_parser("suggest-revisions", help="Convert review/critic JSON into section-targeted revision suggestions")
    suggest_parser.add_argument("--source-paper", required=True)
    suggest_parser.add_argument("--review", required=True)
    suggest_parser.add_argument("--section-review")
    suggest_parser.add_argument("--citation-review")
    suggest_parser.add_argument("--output", required=True)

    critique_parser = sub.add_parser("critique", help="Run paper, section, citation critics and produce revision suggestions")
    critique_parser.add_argument("--source-paper")
    critique_parser.add_argument("--output-dir")
    critique_parser.add_argument(
        "--citation-evidence-mode",
        default="heuristic",
        choices=["heuristic", "model", "web"],
        help="Evidence mode for the citation-support critic used by critique.",
    )
    _runtime_mode_args(critique_parser, strict_flag=True)
    _common_provider_args(critique_parser)

    refine_parser = sub.add_parser("refine", help="Run the refinement loop")
    refine_parser.add_argument("--iterations", type=int, default=1)
    refine_parser.add_argument("--require-compile-for-accept", action="store_true")
    refine_parser.add_argument("--claim-safe", action="store_true", help="Fail closed on claim-safe citation/source prompt contract violations.")
    _runtime_mode_args(refine_parser, strict_flag=True)
    _common_provider_args(refine_parser)

    run_parser = sub.add_parser("run", help="Run the full PaperOrchestra pipeline")
    run_parser.add_argument("--discovery-mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    run_parser.add_argument("--verify-mode", default="live", choices=["live", "mock"])
    run_parser.add_argument("--verify-error-policy", default="skip", choices=["skip", "fail"])
    run_parser.add_argument("--verify-fallback-mode", default="none", choices=["none", "mock"], help="If live verification fails, optionally fall back to mock verification instead of aborting.")
    run_parser.add_argument("--require-live-verification", action="store_true", help="Treat skipped live citation verification as a blocking reproducibility failure.")
    run_parser.add_argument("--refine-iterations", type=int, default=1)
    run_parser.add_argument("--compile", action="store_true")
    _runtime_mode_args(run_parser, strict_flag=True)
    run_parser.add_argument("--full-fidelity", action="store_true", help="Write eval/comparison/fidelity artifacts after the run")
    run_parser.add_argument("--reference-case", help="Reference benchmark case JSON for --full-fidelity comparison artifacts")
    _common_provider_args(run_parser)

    return parser


def _provider_from_args(args: argparse.Namespace):
    return get_provider(args.provider, command=args.provider_command)


@contextmanager
def _strict_omx_env(enabled: bool):
    if not enabled:
        yield
        return
    previous = os.environ.get("PAPERO_STRICT_OMX_NATIVE")
    os.environ["PAPERO_STRICT_OMX_NATIVE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PAPERO_STRICT_OMX_NATIVE", None)
        else:
            os.environ["PAPERO_STRICT_OMX_NATIVE"] = previous


def _write_full_fidelity_artifacts(cwd: Path, reference_case: str | None) -> dict[str, str]:
    current_session_id = get_current_session_id(cwd)
    state = load_session(cwd)
    artifact_dir = cwd / ".paper-orchestra" / "runs" / current_session_id / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "session_eval_summary": str(write_session_eval_summary(cwd, artifact_dir / "session_eval_summary.json")),
        "review_gate_comparison": str(write_review_gate_comparison(cwd, artifact_dir / "review_gate_comparison.json")),
        "generated_citation_titles": str(write_generated_citation_titles(cwd, artifact_dir / "generated_citation_titles.json")),
    }
    if state.artifacts.paper_full_tex and state.artifacts.citation_map_json:
        citation_map = json.loads(Path(state.artifacts.citation_map_json).read_text(encoding="utf-8"))
        references = [
            {"title": entry.get("title"), "citation_key": key}
            for key, entry in citation_map.items()
            if isinstance(entry, dict) and isinstance(entry.get("title"), str) and entry.get("title", "").strip()
        ]
        paths["citation_partition_request"] = str(
            write_citation_partition_request(
                Path(state.artifacts.paper_full_tex).read_text(encoding="utf-8"),
                references,
                artifact_dir / "citation_partition_request.json",
            )
        )
    if reference_case:
        reference_case_path = Path(reference_case).resolve()
        paths["reference_case_partition_scaffold"] = str(
            write_reference_case_partition_scaffold(reference_case_path, artifact_dir / "reference_case_partition_scaffold.json")
        )
        paths["reference_case_partitioned_citation_coverage"] = str(
            write_reference_case_partitioned_citation_coverage(
                reference_case_path,
                cwd,
                artifact_dir / "reference_case_partitioned_citation_coverage.json",
            )
        )
        paths["reference_comparison"] = str(write_reference_comparison(reference_case_path, cwd, artifact_dir / "reference_comparison.json"))
    fidelity_path, _ = record_fidelity_report(cwd)
    paths["fidelity_audit"] = str(fidelity_path)
    paths["session_eval_summary"] = str(write_session_eval_summary(cwd, artifact_dir / "session_eval_summary.json"))
    if reference_case:
        paths["reference_comparison"] = str(write_reference_comparison(Path(reference_case).resolve(), cwd, artifact_dir / "reference_comparison.json"))
    return paths


def _path_or_missing(value: str | None) -> str:
    return value if value else "missing"


def _session_artifact_dir(cwd: Path, state) -> Path:
    if state.artifacts.paper_full_tex:
        return Path(state.artifacts.paper_full_tex).resolve().parent
    return run_dir(cwd, state.session_id) / "artifacts"


def _status_summary_lines(cwd: Path, payload: dict[str, object]) -> list[str]:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    recovery = payload.get("session_recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    artifact_dir = Path(str(artifacts.get("paper_full_tex"))).resolve().parent if artifacts.get("paper_full_tex") else run_dir(cwd, str(payload["session_id"])) / "artifacts"
    lines = [
        f"Session: {payload['session_id']}",
        f"Phase: {payload['current_phase']}",
        "",
        "Main files:",
        f"  TeX: {_path_or_missing(artifacts.get('paper_full_tex'))}",
        f"  PDF: {_path_or_missing(artifacts.get('compiled_pdf'))}",
        f"  Review: {_path_or_missing(artifacts.get('latest_review_json'))}",
        f"  Reproducibility: {_path_or_missing(artifacts.get('latest_reproducibility_json'))}",
        f"  Artifact directory: {artifact_dir}",
        "",
        "Next:",
    ]
    next_commands = recovery.get("next_commands")
    if isinstance(next_commands, list) and next_commands:
        lines.extend(f"  {command}" for command in next_commands)
    elif not artifacts.get("compiled_pdf"):
        lines.extend(
            [
                "  paperorchestra check-compile-env",
                "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile",
            ]
        )
    else:
        lines.append("  paperorchestra export-artifacts --output ./paperorchestra-output")
    return lines


def _copy_if_present(label: str, source: str | None, destination: Path, copied: list[dict[str, str]], skipped: list[dict[str, str]]) -> None:
    if not source:
        skipped.append({"label": label, "reason": "not recorded"})
        return
    source_path = Path(source)
    if not source_path.exists():
        skipped.append({"label": label, "source": str(source_path), "reason": "missing on disk"})
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    copied.append({"label": label, "source": str(source_path), "destination": str(destination)})


def _export_current_artifacts(cwd: Path, output: str | Path, *, include_all_artifacts: bool = False) -> dict[str, object]:
    state = load_session(cwd)
    output_dir = Path(output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    artifacts = state.artifacts
    export_map = [
        ("paper_full_tex", artifacts.paper_full_tex, output_dir / "paper.full.tex"),
        ("compiled_pdf", artifacts.compiled_pdf, output_dir / "paper.full.pdf"),
        ("references_bib", artifacts.references_bib, output_dir / "references.bib"),
        ("latest_review_json", artifacts.latest_review_json, output_dir / "review.latest.json"),
        ("latest_reproducibility_json", artifacts.latest_reproducibility_json, output_dir / "reproducibility.audit.json"),
        ("latest_fidelity_json", artifacts.latest_fidelity_json, output_dir / "fidelity.audit.json"),
        ("latest_runtime_parity_json", artifacts.latest_runtime_parity_json, output_dir / "runtime-parity.json"),
        ("latest_compile_report_json", artifacts.latest_compile_report_json, output_dir / "compile-report.json"),
        ("quality_gate_report", str(artifact_path(cwd, "quality-gate.report.json")), output_dir / "quality-gate.report.json"),
        ("session_json", str(run_dir(cwd, state.session_id) / "session.json"), output_dir / "session.json"),
    ]
    for label, source, destination in export_map:
        _copy_if_present(label, source, destination, copied, skipped)

    if include_all_artifacts:
        artifact_dir = _session_artifact_dir(cwd, state)
        if artifact_dir.exists():
            shutil.copytree(artifact_dir, output_dir / "artifacts", dirs_exist_ok=True)
            copied.append({"label": "artifacts_dir", "source": str(artifact_dir), "destination": str(output_dir / "artifacts")})
        else:
            skipped.append({"label": "artifacts_dir", "source": str(artifact_dir), "reason": "missing on disk"})

    return {
        "status": "ok",
        "session_id": state.session_id,
        "output_dir": str(output_dir),
        "copied": copied,
        "skipped": skipped,
    }


def _ok_warn(value: bool) -> str:
    return "OK" if value else "WARN"


def _environment_summary_lines(payload: dict[str, object]) -> list[str]:
    package_context = payload.get("package_context")
    if not isinstance(package_context, dict):
        package_context = {}
    profiles = payload.get("readiness_profiles")
    if not isinstance(profiles, list):
        profiles = []
    mcp_health = payload.get("paperorchestra_mcp_health")
    if not isinstance(mcp_health, dict):
        mcp_health = {}
    mcp_config = mcp_health.get("config") if isinstance(mcp_health.get("config"), dict) else {}
    mcp_server = mcp_health.get("server") if isinstance(mcp_health.get("server"), dict) else {}
    mcp_attachment = mcp_health.get("active_session_attachment") if isinstance(mcp_health.get("active_session_attachment"), dict) else {}

    lines = [
        "PaperOrchestra environment summary",
        "",
        "Package:",
        f"  Python: {package_context.get('python_executable', 'unknown')}",
        f"  Package root: {package_context.get('package_root', 'unknown')}",
        "",
        "Readiness:",
    ]
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        ready = bool(profile.get("ready"))
        lines.append(f"  {_ok_warn(ready)} {profile.get('name')}: {profile.get('status')}")
        missing = profile.get("missing")
        if isinstance(missing, list) and missing:
            lines.append(f"    missing: {'; '.join(str(item) for item in missing[:2])}")

    lines.extend(
        [
            "",
            "MCP:",
            f"  {_ok_warn(bool(mcp_config.get('registered')))} config registered: {mcp_config.get('registered', False)}",
            f"  {_ok_warn(bool(mcp_server.get('ok')))} stdio server health: {mcp_server.get('ok', False)}",
            f"  active Codex session attachment: not checked ({mcp_attachment.get('detail', 'cannot be verified from CLI')})",
            "",
            "Next:",
            "  ./scripts/demo-mock.sh --in-repo",
            "  paperorchestra doctor",
            "  scripts/smoke-paperorchestra-mcp.py",
        ]
    )
    return lines



def _orchestrator_summary_lines(payload: dict[str, object]) -> list[str]:
    actions = payload.get("next_actions")
    if not isinstance(actions, list):
        actions = []
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scorecard = payload.get("scorecard_summary") if isinstance(payload.get("scorecard_summary"), dict) else {}
    first_action = actions[0].get("action_type") if actions and isinstance(actions[0], dict) else "none"
    lines = [
        "PaperOrchestra orchestrator state",
        render_scorecard_summary(scorecard) if scorecard else "Score: unscored",
        f"Readiness: {readiness.get('label', 'unknown')}",
        f"Next action: {first_action}",
    ]
    return lines


def _print_orchestrator_payload(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        state_payload = payload.get("state") if isinstance(payload.get("state"), dict) else payload
        print("\n".join(_orchestrator_summary_lines(state_payload)))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cwd = Path.cwd()

    try:
        if args.command == "init":
            state = create_session(
                cwd,
                InputBundle(
                    idea_path=str(Path(args.idea).resolve()),
                    experimental_log_path=str(Path(args.experimental_log).resolve()),
                    template_path=str(Path(args.template).resolve()),
                    guidelines_path=str(Path(args.guidelines).resolve()),
                    figures_dir=str(Path(args.figures_dir).resolve()) if args.figures_dir else None,
                    cutoff_date=args.cutoff_date,
                    venue=args.venue,
                    page_limit=args.page_limit,
                ),
                allow_outside_workspace=args.allow_outside_workspace,
            )
            print(state.session_id)
            return 0

        if args.command == "inspect-state":
            state = orchestrator_inspect_state(cwd, material_path=args.material)
            _print_orchestrator_payload(state.to_public_dict(), json_output=args.json)
            return 0

        if args.command == "orchestrate":
            state = orchestrator_run_until_blocked(cwd, material_path=args.material)
            payload = {"execution": "bounded_plan_only", "state": state.to_public_dict()}
            if args.write_evidence:
                payload["evidence_bundle"] = write_orchestrator_evidence_bundle(cwd, state, output_dir=args.evidence_output)
            _print_orchestrator_payload(payload, json_output=args.json)
            return 0

        if args.command == "continue-project":
            state = orchestrator_run_until_blocked(cwd)
            payload = {"execution": "bounded_plan_only", "state": state.to_public_dict()}
            _print_orchestrator_payload(payload, json_output=args.json)
            return 0

        if args.command == "answer-human-needed":
            state = orchestrator_inspect_state(cwd)
            payload = {
                "execution": "answer_recorded_for_re_adjudication",
                "answer": "redacted" if args.answer else "missing",
                "state": state.to_public_dict(),
                "next_actions": [{"action_type": "re_adjudicate", "reason": "human_needed_answer_received"}],
            }
            _print_orchestrator_payload(payload, json_output=args.json)
            return 0

        if args.command == "status":
            state = load_session(cwd)
            payload = state.to_dict()
            payload["session_recovery"] = build_session_recovery_hint(cwd)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            elif args.summary:
                print("\n".join(_status_summary_lines(cwd, payload)))
            else:
                print(f"session_id: {payload['session_id']}")
                print(f"current_phase: {payload['current_phase']}")
                print(f"active_artifact: {payload['active_artifact']}")
                print(f"refinement_iteration: {payload['refinement_iteration']}")
                print(f"latest_validation_json: {payload['artifacts'].get('latest_validation_json')}")
                print(f"latest_fidelity_json: {payload['artifacts'].get('latest_fidelity_json')}")
                print(f"latest_compile_env_json: {payload['artifacts'].get('latest_compile_env_json')}")
                print(f"latest_compile_report_json: {payload['artifacts'].get('latest_compile_report_json')}")
                print(f"latest_runtime_parity_json: {payload['artifacts'].get('latest_runtime_parity_json')}")
                print(f"latest_lane_summary_json: {payload['artifacts'].get('latest_lane_summary_json')}")
                print(f"latest_reproducibility_json: {payload['artifacts'].get('latest_reproducibility_json')}")
                print(f"latest_provider_identity_json: {payload['artifacts'].get('latest_provider_identity_json')}")
                print(f"latest_figure_placement_review_json: {payload['artifacts'].get('latest_figure_placement_review_json')}")
                print(f"latest_section_review_json: {payload['artifacts'].get('latest_section_review_json')}")
                print(f"latest_prompt_trace_dir: {payload['artifacts'].get('latest_prompt_trace_dir')}")
                print(f"latest_verification_errors_json: {payload['artifacts'].get('latest_verification_errors_json')}")
                recovery = payload["session_recovery"]
                print(f"recovery_status: {recovery.get('status')}")
                if recovery.get("next_commands"):
                    print("next_commands:")
                    for command in recovery["next_commands"]:
                        print(f"  - {command}")
                print(f"artifacts: {json.dumps(payload['artifacts'], indent=2, ensure_ascii=False)}")
            return 0

        if args.command in {"export-artifacts", "export-current"}:
            payload = _export_current_artifacts(cwd, args.output, include_all_artifacts=args.include_all_artifacts)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"Exported PaperOrchestra outputs for session {payload['session_id']}")
                print(f"Output: {payload['output_dir']}")
                print("Copied:")
                for item in payload["copied"]:
                    print(f"  - {item['label']}: {item['destination']}")
                if payload["skipped"]:
                    print("Skipped:")
                    for item in payload["skipped"]:
                        reason = item.get("reason", "unknown")
                        print(f"  - {item['label']}: {reason}")
            return 0

        if args.command == "quickstart":
            guides = {
                "new-paper": [
                    "1. Prepare idea.md, experimental_log.md, template.tex, and conference_guidelines.md.",
                    "2. Run: paperorchestra init --idea ... --experimental-log ... --template ... --guidelines ...",
                    "3. Optional: paperorchestra research-prior-work / import-prior-work for curated citations.",
                    "4. Run: paperorchestra run --provider mock --verify-mode mock --compile --full-fidelity",
                    "5. Run: paperorchestra critique --provider mock --source-paper <your-main.tex>",
                    "6. Run: paperorchestra audit-reproducibility  # classify whether the current run is claim-safe",
                ],
                "testset": [
                    "1. Run: paperorchestra init --idea examples/minimal/idea.md --experimental-log examples/minimal/experimental_log.md --template examples/minimal/template.tex --guidelines examples/minimal/conference_guidelines.md",
                    "2. Optional: paperorchestra research-prior-work --provider mock --source codex_web_seed --import",
                    "3. Run: paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility --compile --full-fidelity",
                    "4. Run: paperorchestra review-sections --provider mock && paperorchestra review-citations --provider mock",
                    "5. Run: paperorchestra audit-reproducibility",
                ],
                "curated-prior-work": [
                    "1. Use Codex/web/manual review to create prior_work.json, references.bib, or prior_work.md.",
                    "2. Run: paperorchestra import-prior-work --seed-file prior_work.json --source codex_web_seed",
                    "3. Continue with write-intro-related, write-sections, compile, review, and refine.",
                ],
                "environment": [
                    "1. Read: ENVIRONMENT.md",
                    "2. Copy the README 'Copyable environment template' block into a local .env (or export only what you need)",
                    "3. Run: paperorchestra environment  # canonical inventory + readiness profiles",
                    "4. Run: paperorchestra doctor       # what is missing on this machine right now?",
                    "5. If you need PDFs: paperorchestra check-compile-env && paperorchestra bootstrap-compile-env",
                ],
            }
            print(json.dumps({"scenario": args.scenario, "steps": guides[args.scenario]}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "teach":
            print(json.dumps(prepare_teach_bundle(
                cwd,
                paper=args.paper,
                output_dir=args.output_dir,
                artifact_repo=args.artifact_repo,
                figures_dir=args.figures_dir,
                pdf=args.pdf,
                initialize_session=not args.no_init_session,
                allow_outside_workspace=args.allow_outside_workspace,
            ), indent=2, ensure_ascii=False))
            return 0

        if args.command == "intake-start":
            seed_answers = json.loads(args.seed_answers) if args.seed_answers else None
            print(json.dumps(start_intake(cwd, seed_answers=seed_answers), indent=2, ensure_ascii=False))
            return 0

        if args.command == "intake-status":
            print(json.dumps(get_intake_status(cwd, intake_id=args.intake_id), indent=2, ensure_ascii=False))
            return 0

        if args.command == "intake-review":
            print(json.dumps(get_intake_review(cwd, intake_id=args.intake_id), indent=2, ensure_ascii=False))
            return 0

        if args.command == "intake-answer":
            answers = json.loads(args.answers_json) if args.answers_json else None
            print(
                json.dumps(
                    answer_intake_question(
                        cwd,
                        intake_id=args.intake_id,
                        key=args.key,
                        answer=args.answer,
                        answers=answers,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "intake-research":
            print(
                json.dumps(
                    research_prior_work(
                        cwd,
                        intake_id=args.intake_id,
                        mode=args.mode,
                        max_per_seed=args.max_per_seed,
                        allow_outside_workspace=args.allow_outside_workspace,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "intake-finalize":
            print(
                json.dumps(
                    finalize_intake(
                        cwd,
                        intake_id=args.intake_id,
                        output_dir=args.output_dir,
                        template_path=args.template_path,
                        figures_dir=args.figures_dir,
                        initialize_session=not args.no_init_session,
                        allow_overwrite=args.allow_overwrite,
                        allow_outside_workspace=args.allow_outside_workspace,
                        selected_story_candidate_id=args.story_candidate_id,
                        selected_claim_candidate_ids=args.claim_candidate_ids,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "intake-approve":
            print(
                json.dumps(
                    approve_intake_direction(
                        cwd,
                        intake_id=args.intake_id,
                        story_candidate_id=args.story_candidate_id,
                        claim_candidate_ids=args.claim_candidate_ids,
                        output_dir=args.output_dir,
                        template_path=args.template_path,
                        figures_dir=args.figures_dir,
                        initialize_session=not args.no_init_session,
                        allow_overwrite=args.allow_overwrite,
                        allow_outside_workspace=args.allow_outside_workspace,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "job-start-run":
            with _strict_omx_env(args.strict_omx_native):
                print(
                    json.dumps(
                        start_run_job(
                            cwd,
                            provider=args.provider,
                            provider_command=args.provider_command,
                            discovery_mode=args.discovery_mode,
                            verify_mode=args.verify_mode,
                            verify_error_policy=args.verify_error_policy,
                            verify_fallback_mode=args.verify_fallback_mode,
                            require_live_verification=args.require_live_verification,
                            refine_iterations=args.refine_iterations,
                            compile_paper=args.compile,
                            runtime_mode=args.runtime_mode,
                        ),
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            return 0

        if args.command == "jobs-list":
            print(json.dumps(list_jobs(cwd, limit=args.limit), indent=2, ensure_ascii=False))
            return 0

        if args.command in {"job-status", "run-status"}:
            print(json.dumps(get_job_status(cwd, args.job_id), indent=2, ensure_ascii=False))
            return 0

        if args.command in {"job-tail-log", "run-tail-log"}:
            print(json.dumps(tail_job_log(cwd, args.job_id, lines=args.lines), indent=2, ensure_ascii=False))
            return 0

        if args.command == "job-cancel":
            print(json.dumps(cancel_job(cwd, args.job_id), indent=2, ensure_ascii=False))
            return 0

        if args.command == "outline":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                print(generate_outline(cwd, provider, runtime_mode=args.runtime_mode))
            return 0

        if args.command == "generate-plots":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                print(generate_plots(cwd, provider, runtime_mode=args.runtime_mode))
            return 0

        if args.command == "discover-papers":
            provider = _provider_from_args(args) if args.mode == "model" else None
            with _strict_omx_env(args.strict_omx_native):
                print(discover_papers(cwd, provider=provider, mode=args.mode, runtime_mode=args.runtime_mode))
            return 0

        if args.command == "import-prior-work":
            print(json.dumps(
                import_prior_work(
                    cwd,
                    seed_file=args.seed_file,
                    source=args.source,
                    require_complete_metadata=args.require_complete_metadata,
                ),
                indent=2,
                ensure_ascii=False,
            ))
            return 0

        if args.command == "plan-narrative":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                paths = plan_narrative_and_claims(cwd, provider, runtime_mode=args.runtime_mode)
            print(json.dumps({key: str(path) for key, path in paths.items()}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "research-prior-work":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                print(json.dumps(generate_prior_work_seed(
                    cwd,
                    provider,
                    output=args.output,
                    paper=args.paper,
                    artifact_repo=args.artifact_repo,
                    runtime_mode=args.runtime_mode,
                    source=args.source,
                    import_seed=args.import_seed,
                    require_complete_metadata=args.require_complete_metadata,
                ), indent=2, ensure_ascii=False))
            return 0

        if args.command == "verify-papers":
            print(verify_papers(cwd, min_ratio=args.min_ratio, mode=args.mode, on_error=args.on_error))
            return 0

        if args.command == "build-bib":
            print(build_bib(cwd))
            return 0

        if args.command == "write-intro-related":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                print(
                    write_intro_related(
                        cwd,
                        provider,
                        runtime_mode=args.runtime_mode,
                        claim_safe=args.claim_safe,
                        allow_recoverable_contract_issues=args.allow_recoverable_contract_issues,
                    )
                )
            return 0

        if args.command == "write-sections":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                print(
                    write_sections(
                        cwd,
                        provider,
                        runtime_mode=args.runtime_mode,
                        only_sections=args.only_sections,
                        output_path=args.output_tex,
                        claim_safe=args.claim_safe,
                    )
                )
            return 0

        if args.command == "compile":
            print(compile_current_paper(cwd))
            return 0

        if args.command == "check-compile-env":
            path, payload = record_compile_environment_report(cwd)
            print(json.dumps({"path": str(path), "report": payload, **payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "bootstrap-compile-env":
            report = inspect_compile_environment(cwd)
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return 0

        if args.command == "environment":
            inventory = build_environment_inventory()
            doctor = build_doctor_report(cwd)
            payload = {
                **inventory,
                "readiness_profiles": doctor["readiness_profiles"],
                "paperorchestra_mcp_health": doctor.get("paperorchestra_mcp_health"),
                "next_steps": [
                    "paperorchestra doctor",
                    "paperorchestra quickstart --scenario new-paper",
                    "paperorchestra quickstart --scenario testset",
                ],
            }
            if args.summary:
                print("\n".join(_environment_summary_lines(payload)))
            else:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.command == "doctor":
            payload = build_doctor_report(cwd, omx_deep=args.omx_deep, omx_timeout=args.omx_timeout)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.command == "export-omx-evidence":
            print(json.dumps(export_omx_evidence(cwd, args.output, timeout=args.timeout), indent=2, ensure_ascii=False))
            return 0

        if args.command == "omx-review-handoff":
            path, payload = write_omx_review_handoff(cwd, output_path=args.output)
            print(json.dumps({"path": str(path), **payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "cleanup-tmp":
            print(json.dumps(cleanup_omx_tmp(cwd, max_age_seconds=args.max_age_seconds), indent=2, ensure_ascii=False))
            return 0

        if args.command == "review":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                print(review_current_paper(cwd, provider, review_name=args.output or "review.latest.json", runtime_mode=args.runtime_mode))
            return 0

        if args.command == "review-sections":
            print(write_section_review(cwd, args.output))
            return 0

        if args.command == "review-citations":
            citation_provider = get_citation_support_provider(
                args.provider,
                command=args.provider_command,
                evidence_mode=args.evidence_mode,
            )
            print(
                write_citation_support_review(
                    cwd,
                    args.output,
                    provider=citation_provider,
                    evidence_mode=args.evidence_mode,
                )
            )
            return 0

        if args.command == "audit-rendered-references":
            path, payload = write_rendered_reference_audit(cwd, quality_mode=args.quality_mode)
            if args.output:
                extra_path = Path(args.output).resolve()
                if extra_path != path:
                    write_json(extra_path, payload)
                    path = extra_path
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "audit-citation-integrity":
            path, payload = write_citation_integrity_audit(cwd, quality_mode=args.quality_mode, output_path=args.output)
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "audit-citation-integrity-critic":
            path, payload = write_citation_integrity_critic(cwd, quality_mode=args.quality_mode, output_path=args.output)
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "review-figure-placement":
            path, payload = write_figure_placement_review(cwd, output_path=args.output)
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "validate-current":
            name = Path(args.output).name if args.output else "validation.current.json"
            path, payload = record_current_validation_report(cwd, name=name)
            if args.output and Path(args.output).resolve() != path:
                Path(args.output).resolve().write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                path = Path(args.output).resolve()
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "validate-claim-safe-current":
            structural_name = "validation.claim-safe.structural.json"
            structural_path, structural_payload = record_current_validation_report(cwd, name=structural_name)
            quality_path, quality_payload = write_quality_eval(
                cwd,
                quality_mode="claim_safe",
                max_iterations=args.max_iterations,
                require_live_verification=args.require_live_verification,
            )
            plan_path, plan_payload = write_quality_loop_plan(
                cwd,
                quality_mode="claim_safe",
                max_iterations=args.max_iterations,
                require_live_verification=args.require_live_verification,
                quality_eval_input_path=quality_path,
            )
            payload = {
                "schema_version": "claim-safe-validation/1",
                "structural_validation": {
                    "path": str(structural_path),
                    "ok": structural_payload.get("ok"),
                    "blocking_issue_count": structural_payload.get("blocking_issue_count"),
                },
                "quality_eval": {
                    "path": str(quality_path),
                    "verdict_inputs": quality_payload.get("tiers"),
                },
                "qa_loop_plan": {
                    "path": str(plan_path),
                    "verdict": plan_payload.get("verdict"),
                    "verdict_rationale": plan_payload.get("verdict_rationale"),
                    "repair_actions": plan_payload.get("repair_actions"),
                    "human_handoff": plan_payload.get("human_handoff"),
                },
                "ok": bool(structural_payload.get("ok")) and plan_payload.get("verdict") == "ready_for_human_finalization",
            }
            output_path = Path(args.output).resolve() if args.output else Path(structural_path).with_name("validation.claim-safe-current.json")
            output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({"path": str(output_path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "build-source-obligations":
            print(write_source_obligations(cwd, args.output))
            return 0

        if args.command == "audit-fidelity":
            path, payload = record_fidelity_report(cwd)
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "audit-reproducibility":
            output_path = Path(args.output).resolve() if args.output else None
            path, payload = write_reproducibility_audit(
                cwd,
                output_path,
                require_live_verification=args.require_live_verification,
            )
            print(json.dumps({"path": str(path), "report": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "quality-eval":
            output_path = Path(args.output).resolve() if args.output else None
            path, payload = write_quality_eval(
                cwd,
                output_path,
                require_live_verification=args.require_live_verification,
                quality_mode=args.quality_mode,
                max_iterations=args.max_iterations,
                append_history=args.record_history,
            )
            print(json.dumps({"path": str(path), "quality_eval": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "quality-gate":
            output_path = Path(args.output).resolve() if args.output else None
            plan_output_path = Path(args.plan_output).resolve() if args.plan_output else None
            provider = _provider_from_args(args) if args.auto_refine else None
            with _strict_omx_env(args.strict_omx_native):
                path, payload = write_quality_gate(
                    cwd,
                    output_path,
                    plan_output_path=plan_output_path,
                    profile=args.profile,
                    quality_mode=args.quality_mode,
                    require_live_verification=args.require_live_verification,
                    accept_mixed_provenance=args.accept_mixed_provenance,
                    max_iterations=args.max_iterations,
                    auto_refine=args.auto_refine,
                    provider=provider,
                    refine_iterations=args.refine_iterations,
                    runtime_mode=args.runtime_mode,
                    require_compile_for_accept=args.require_compile_for_accept,
                )
            print(json.dumps({"path": str(path), "quality_gate": payload}, indent=2, ensure_ascii=False))
            if payload.get("decision", {}).get("blocked") and not args.no_fail_on_block:
                return 10
            return 0

        if args.command in {"qa-loop-plan", "qa-loop"}:
            output_path = Path(args.output).resolve() if args.output else None
            path, payload = write_quality_loop_plan(
                cwd,
                output_path,
                require_live_verification=args.require_live_verification,
                quality_mode=args.quality_mode,
                max_iterations=args.max_iterations,
                accept_mixed_provenance=args.accept_mixed_provenance,
                quality_eval_input_path=args.quality_eval,
            )
            print(json.dumps({"path": str(path), "plan": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "qa-loop-brief":
            output_path = Path(args.output).resolve() if args.output else None
            path, brief = write_qa_loop_brief(
                cwd,
                output_path,
                require_live_verification=args.require_live_verification,
                quality_mode=args.quality_mode,
                max_iterations=args.max_iterations,
                accept_mixed_provenance=args.accept_mixed_provenance,
                quality_eval_path=args.quality_eval,
                plan_path=args.qa_loop_plan,
            )
            print(json.dumps({"path": str(path), "brief": brief}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "repair-citation-claims":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                payload = repair_citation_claims(
                    cwd,
                    provider,
                    citation_review_path=args.citation_review,
                    runtime_mode=args.runtime_mode,
                    require_compile=args.require_compile,
                )
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if payload.get("accepted") else 1

        if args.command == "qa-loop-step":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                result = run_qa_loop_step(
                    cwd,
                    provider,
                    quality_mode=args.quality_mode,
                    max_iterations=args.max_iterations,
                    require_live_verification=args.require_live_verification,
                    accept_mixed_provenance=args.accept_mixed_provenance,
                    runtime_mode=args.runtime_mode,
                    require_compile=args.require_compile,
                    citation_evidence_mode=args.citation_evidence_mode,
                    citation_provider_name=args.citation_provider or args.provider,
                    citation_provider_command=args.citation_provider_command if args.citation_provider_command is not None else args.provider_command,
                )
            print(json.dumps({"path": str(result.path), "execution": result.payload}, indent=2, ensure_ascii=False))
            return result.exit_code

        if args.command == "ralph-start":
            if args.dry_run and args.launch:
                parser.error("ralph-start accepts either --dry-run or --launch, not both")
            output_path = Path(args.output).resolve() if args.output else None
            payload = build_ralph_start_payload(
                cwd,
                quality_mode=args.quality_mode,
                max_iterations=args.max_iterations,
                output_path=output_path,
                require_live_verification=args.require_live_verification,
                accept_mixed_provenance=args.accept_mixed_provenance,
                evidence_root=args.evidence_root,
            )
            if args.launch:
                proc = launch_omx_ralph(payload["argv"], cwd=cwd)
                payload["launch"] = {"pid": proc.pid, "status": "started"}
            else:
                payload["launch"] = {"status": "dry_run"}
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.command == "build-operator-review-packet":
            path, payload = build_operator_review_packet(
                cwd,
                output_path=args.output,
                require_pdf=args.require_pdf,
                review_scope=args.review_scope,
            )
            print(json.dumps({"path": str(path), "packet": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "import-operator-feedback":
            path, payload = import_operator_feedback(
                cwd,
                packet_path=args.packet,
                feedback_path=args.feedback,
                output_path=args.output,
            )
            print(json.dumps({"path": str(path), "imported_feedback": payload}, indent=2, ensure_ascii=False))
            return 0

        if args.command == "apply-operator-feedback":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                path, payload = apply_operator_feedback(
                    cwd,
                    provider,
                    imported_feedback_path=args.imported_feedback,
                    max_supervised_iterations=args.max_supervised_iterations,
                    require_compile=args.require_compile,
                    quality_mode=args.quality_mode,
                    max_iterations=args.max_iterations,
                    require_live_verification=args.require_live_verification,
                    accept_mixed_provenance=args.accept_mixed_provenance,
                    runtime_mode=args.runtime_mode,
                    citation_evidence_mode=args.citation_evidence_mode,
                    citation_provider_name=args.citation_provider,
                    citation_provider_command=args.citation_provider_command,
                )
            print(json.dumps({"path": str(path), "execution": payload}, indent=2, ensure_ascii=False))
            return 0 if payload.get("verdict") != "execution_error" else 1

        if args.command == "estimate-cost":
            print(
                json.dumps(
                    estimate_run_cost(
                        cwd,
                        discovery_mode=args.discovery_mode,
                        refine_iterations=args.refine_iterations,
                        compile_paper=args.compile,
                        runtime_mode=args.runtime_mode,
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "build-reference-benchmark-case":
            reference_dir = Path(args.reference_dir).resolve()
            output_path = Path(args.output).resolve() if args.output else reference_dir / "benchmark_case.json"
            print(write_reference_benchmark_case(reference_dir, output_path, source_pdf=args.source_pdf))
            return 0

        if args.command == "build-session-eval-summary":
            current_session_id = get_current_session_id(cwd)
            output_path = Path(args.output).resolve() if args.output else cwd / ".paper-orchestra" / "runs" / current_session_id / "artifacts" / "session_eval_summary.json"
            print(write_session_eval_summary(cwd, output_path))
            return 0

        if args.command == "build-review-gate-comparison":
            current_session_id = get_current_session_id(cwd)
            output_path = Path(args.output).resolve() if args.output else cwd / ".paper-orchestra" / "runs" / current_session_id / "artifacts" / "review_gate_comparison.json"
            print(write_review_gate_comparison(cwd, output_path))
            return 0

        if args.command == "build-generated-citation-titles":
            current_session_id = get_current_session_id(cwd)
            output_path = Path(args.output).resolve() if args.output else cwd / ".paper-orchestra" / "runs" / current_session_id / "artifacts" / "generated_citation_titles.json"
            print(write_generated_citation_titles(cwd, output_path))
            return 0

        if args.command == "compare-reference-case":
            current_session_id = get_current_session_id(cwd)
            output_path = Path(args.output).resolve() if args.output else cwd / ".paper-orchestra" / "runs" / current_session_id / "artifacts" / "reference_comparison.json"
            print(write_reference_comparison(Path(args.reference_case).resolve(), cwd, output_path))
            return 0

        if args.command == "build-reference-case-partition-scaffold":
            output_path = Path(args.output).resolve() if args.output else Path(args.reference_case).resolve().with_name("reference_case_partition_scaffold.json")
            print(write_reference_case_partition_scaffold(Path(args.reference_case).resolve(), output_path))
            return 0

        if args.command == "compare-reference-case-citation-coverage":
            current_session_id = get_current_session_id(cwd)
            output_path = Path(args.output).resolve() if args.output else cwd / ".paper-orchestra" / "runs" / current_session_id / "artifacts" / "reference_case_partitioned_citation_coverage.json"
            print(write_reference_case_partitioned_citation_coverage(Path(args.reference_case).resolve(), cwd, output_path))
            return 0

        if args.command == "build-citation-partition-request":
            paper_text = Path(args.paper_text_file).resolve().read_text(encoding="utf-8")
            references = json.loads(Path(args.references_json).resolve().read_text(encoding="utf-8"))
            output_path = Path(args.output).resolve() if args.output else Path(args.references_json).resolve().with_name("citation_partition_request.json")
            print(write_citation_partition_request(paper_text, references, output_path))
            return 0

        if args.command == "compare-partitioned-citation-coverage":
            references = json.loads(Path(args.references_json).resolve().read_text(encoding="utf-8"))
            partition_map = json.loads(Path(args.partition_json).resolve().read_text(encoding="utf-8"))
            generated_titles = json.loads(Path(args.generated_titles_json).resolve().read_text(encoding="utf-8"))
            output_path = Path(args.output).resolve() if args.output else Path(args.partition_json).resolve().with_name("partitioned_citation_coverage.json")
            print(write_partitioned_citation_coverage(references, partition_map, generated_titles, output_path))
            return 0

        if args.command == "suggest-revisions":
            print(
                write_revision_suggestions(
                    args.source_paper,
                    args.review,
                    args.output,
                    section_review_json=args.section_review,
                    citation_review_json=args.citation_review,
                )
            )
            return 0

        if args.command == "critique":
            provider = _provider_from_args(args)
            state = load_session(cwd)
            output_dir = Path(args.output_dir).resolve() if args.output_dir else Path(state.artifacts.paper_full_tex or state.inputs.idea_path).resolve().parent
            output_dir.mkdir(parents=True, exist_ok=True)
            with _strict_omx_env(args.strict_omx_native):
                review_path = review_current_paper(cwd, provider, runtime_mode=args.runtime_mode)
            section_path = write_section_review(cwd, output_dir / "section_review.json")
            citation_provider = get_citation_support_provider(
                args.provider,
                command=args.provider_command,
                evidence_mode=args.citation_evidence_mode,
            )
            citation_path = write_citation_support_review(
                cwd,
                output_dir / "citation_support_review.json",
                provider=citation_provider,
                evidence_mode=args.citation_evidence_mode,
            )
            source_paper = args.source_paper or state.artifacts.paper_full_tex
            suggestions_path = write_revision_suggestions(
                source_paper,
                review_path,
                output_dir / "revision_suggestions.json",
                section_review_json=section_path,
                citation_review_json=citation_path,
            )
            print(json.dumps({
                "review": str(review_path),
                "section_review": str(section_path),
                "citation_support_review": str(citation_path),
                "revision_suggestions": str(suggestions_path),
            }, indent=2, ensure_ascii=False))
            return 0

        if args.command == "refine":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
                result = refine_current_paper(
                    cwd,
                    provider,
                    iterations=args.iterations,
                    require_compile_for_accept=args.require_compile_for_accept,
                    runtime_mode=args.runtime_mode,
                    claim_safe=args.claim_safe,
                )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if any(not item.get("accepted", False) for item in result) else 0

        if args.command == "run":
            provider = _provider_from_args(args)
            with _strict_omx_env(args.strict_omx_native):
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
            if args.full_fidelity:
                result["full_fidelity_artifacts"] = _write_full_fidelity_artifacts(cwd, args.reference_case)
            exit_code = 1 if result.get("status") == "blocked" else 0
            if (
                args.strict_omx_native
                and args.runtime_mode == "omx_native"
                and result.get("runtime_parity", {}).get("overall_status") != "implemented"
            ):
                result["strict_omx_native_violation"] = {
                    "runtime_parity_overall_status": result.get("runtime_parity", {}).get("overall_status"),
                    "runtime_parity_report": result.get("runtime_parity_report"),
                }
                exit_code = 2
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return exit_code

        parser.error(f"Unhandled command: {args.command}")
        return 2
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        if getattr(args, "strict_omx_native", False) and "Strict OMX-native mode forbids fallback" in str(exc):
            return 2
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
