from __future__ import annotations

import argparse

from paperorchestra import __version__


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
    parser = argparse.ArgumentParser(
        prog="paperorchestra",
        description="PaperOrchestra CLI: status, research, critic review, authoring, QA loop, and OMX handoff.",
    )
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
    init_parser.add_argument("--allow-outside-workspace", action="store_true")

    status_parser = sub.add_parser("status", help="Show current session state")
    status_parser.add_argument("--json", action="store_true")
    status_parser.add_argument("--summary", action="store_true")

    inspect_state_parser = sub.add_parser("inspect-state", help="Inspect material readiness and the next orchestration action")
    inspect_state_parser.add_argument("--material")
    inspect_state_parser.add_argument("--json", action="store_true")

    orchestrate_parser = sub.add_parser("orchestrate", help="Run the orchestrator until the next bounded action or stop")
    orchestrate_parser.add_argument("--material")
    orchestrate_mode = orchestrate_parser.add_mutually_exclusive_group()
    orchestrate_mode.add_argument("--execute-local", action="store_true")
    orchestrate_mode.add_argument("--plan-full-loop", action="store_true")
    orchestrate_mode.add_argument("--execute-omx", action="store_true")
    orchestrate_parser.add_argument("--write-evidence", action="store_true")
    orchestrate_parser.add_argument("--evidence-output")
    orchestrate_parser.add_argument("--json", action="store_true")


    answer_parser = sub.add_parser("answer-human-needed", help="Record an answer for a human_needed stop and optionally apply it")
    answer_parser.add_argument("--answer", required=True)
    answer_parser.add_argument("--packet")
    answer_parser.add_argument("--review-scope", choices=["pdf_and_tex", "tex_only"])
    answer_parser.add_argument("--intent", choices=["approve_existing_candidate", "generate_new_operator_candidate", "reject_candidate_with_reason"])
    answer_parser.add_argument("--action-id")
    answer_parser.add_argument("--output-answer")
    answer_parser.add_argument("--output-feedback")
    answer_parser.add_argument("--redacted-answer-only", action="store_true")
    answer_parser.add_argument("--apply", action="store_true")
    answer_parser.add_argument("--imported-feedback-output")
    answer_parser.add_argument("--max-supervised-iterations", type=int, default=1)
    answer_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    answer_parser.add_argument("--max-iterations", type=int, default=10)
    answer_parser.add_argument("--require-live-verification", action="store_true")
    answer_parser.add_argument("--accept-mixed-provenance", action="store_true")
    answer_parser.add_argument("--require-compile", action="store_true")
    answer_parser.add_argument("--citation-evidence-mode", default="web", choices=["heuristic", "model", "web", "source"])
    _runtime_mode_args(answer_parser, strict_flag=True)
    _common_provider_args(answer_parser)
    _citation_provider_args(answer_parser)
    answer_parser.add_argument("--json", action="store_true")

    export_parser = sub.add_parser("export-current", help="Copy current manuscript outputs to a destination directory")
    export_parser.add_argument("--output", required=True)
    export_parser.add_argument("--include-all-artifacts", action="store_true")
    export_parser.add_argument("--json", action="store_true")

    research_parser = sub.add_parser("research-prior-work", help="Generate/import a prior-work seed using the configured provider")
    research_parser.add_argument("--output")
    research_parser.add_argument("--paper")
    research_parser.add_argument("--artifact-repo")
    research_parser.add_argument("--source", default="codex_web_seed")
    research_parser.add_argument("--import", dest="import_seed", action="store_true")
    research_parser.add_argument("--require-complete-metadata", action="store_true")
    _runtime_mode_args(research_parser, strict_flag=True)
    _common_provider_args(research_parser)

    import_parser = sub.add_parser("import-prior-work", help="Import a curated prior-work seed file")
    import_parser.add_argument("--seed-file", required=True)
    import_parser.add_argument("--source", default="manual_seed")
    import_parser.add_argument("--require-complete-metadata", action="store_true")

    sections_parser = sub.add_parser("write-sections", help="Draft or rewrite manuscript sections")
    sections_parser.add_argument("--only-sections")
    sections_parser.add_argument("--output-tex")
    sections_parser.add_argument("--claim-safe", action="store_true")
    _runtime_mode_args(sections_parser, strict_flag=True)
    _common_provider_args(sections_parser)

    sub.add_parser("compile", help="Compile the current manuscript")

    environment_parser = sub.add_parser("environment", help="Show environment-variable and readiness inventory")
    environment_parser.add_argument("--json", action="store_true")
    environment_parser.add_argument("--summary", action="store_true")

    doctor_parser = sub.add_parser("doctor", help="Run a pre-flight environment check")
    doctor_parser.add_argument("--omx-deep", action="store_true")
    doctor_parser.add_argument("--omx-timeout", type=float, default=10.0)

    critique_parser = sub.add_parser("critique", help="Run paper, section, and citation critics")
    critique_parser.add_argument("--source-paper")
    critique_parser.add_argument("--output-dir")
    critique_parser.add_argument("--citation-evidence-mode", default="heuristic", choices=["heuristic", "model", "web", "source"])
    critique_parser.add_argument("--live", action="store_true")
    critique_parser.add_argument("--claim-safe", action="store_true")
    _runtime_mode_args(critique_parser, strict_flag=True)
    _common_provider_args(critique_parser)

    quality_gate_parser = sub.add_parser("quality-gate", help="Run the draft-quality gate")
    quality_gate_parser.add_argument("--output")
    quality_gate_parser.add_argument("--plan-output")
    quality_gate_parser.add_argument("--profile", default="auto", choices=["auto", "mock", "ralph", "claim_safe"])
    quality_gate_parser.add_argument("--quality-mode", default="draft", choices=["draft", "ralph", "claim_safe"])
    quality_gate_parser.add_argument("--max-iterations", type=int, default=10)
    quality_gate_parser.add_argument("--require-live-verification", action="store_true")
    quality_gate_parser.add_argument("--accept-mixed-provenance", action="store_true")
    quality_gate_parser.add_argument("--auto-refine", action="store_true")
    quality_gate_parser.add_argument("--refine-iterations", type=int, default=1)
    quality_gate_parser.add_argument("--require-compile-for-accept", action="store_true")
    quality_gate_parser.add_argument("--no-fail-on-block", action="store_true")
    _runtime_mode_args(quality_gate_parser, strict_flag=True)
    _common_provider_args(quality_gate_parser)

    qa_loop_parser = sub.add_parser("qa-loop", help="Build the next QA-loop repair plan")
    qa_loop_parser.add_argument("--output")
    qa_loop_parser.add_argument("--quality-eval")
    qa_loop_parser.add_argument("--quality-mode", default="ralph", choices=["draft", "ralph", "claim_safe"])
    qa_loop_parser.add_argument("--max-iterations", type=int, default=10)
    qa_loop_parser.add_argument("--accept-mixed-provenance", action="store_true")
    qa_loop_parser.add_argument("--require-live-verification", action="store_true")

    qa_step_parser = sub.add_parser("qa-loop-step", help="Execute one bounded QA-loop repair step")
    qa_step_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    qa_step_parser.add_argument("--max-iterations", type=int, default=10)
    qa_step_parser.add_argument("--accept-mixed-provenance", action="store_true")
    qa_step_parser.add_argument("--require-live-verification", action="store_true")
    qa_step_parser.add_argument("--require-compile", action="store_true")
    qa_step_parser.add_argument("--citation-evidence-mode", default="web", choices=["heuristic", "model", "web", "source"])
    qa_step_parser.add_argument("--quality-eval")
    qa_step_parser.add_argument("--plan")
    qa_step_parser.add_argument("--citation-support-review")
    _runtime_mode_args(qa_step_parser, strict_flag=True)
    _common_provider_args(qa_step_parser)
    _citation_provider_args(qa_step_parser)

    ralph_parser = sub.add_parser("ralph-start", help="Create or launch an OMX Ralph handoff for the current QA loop")
    ralph_parser.add_argument("--output")
    ralph_parser.add_argument("--quality-mode", default="claim_safe", choices=["draft", "ralph", "claim_safe"])
    ralph_parser.add_argument("--max-iterations", type=int, default=10)
    ralph_parser.add_argument("--require-live-verification", action="store_true")
    ralph_parser.add_argument("--accept-mixed-provenance", action="store_true")
    ralph_parser.add_argument("--evidence-root")
    ralph_parser.add_argument("--dry-run", action="store_true")
    ralph_parser.add_argument("--launch", action="store_true")

    run_parser = sub.add_parser("run", help="Run the full PaperOrchestra pipeline")
    run_parser.add_argument("--discovery-mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    run_parser.add_argument("--verify-mode", default="live", choices=["live", "mock"])
    run_parser.add_argument("--verify-error-policy", default="skip", choices=["skip", "fail"])
    run_parser.add_argument("--verify-fallback-mode", default="none", choices=["none", "mock"])
    run_parser.add_argument("--require-live-verification", action="store_true")
    run_parser.add_argument("--refine-iterations", type=int, default=1)
    run_parser.add_argument("--compile", action="store_true")
    _runtime_mode_args(run_parser, strict_flag=True)
    _common_provider_args(run_parser)

    return parser
