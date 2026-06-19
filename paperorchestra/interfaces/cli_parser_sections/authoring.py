from __future__ import annotations

from typing import Any

from paperorchestra.interfaces.cli_parser_sections.common import add_common_provider_args, add_runtime_mode_args


def register_authoring_commands(subparsers: Any) -> None:
    research_parser = subparsers.add_parser("research-prior-work", help="Generate/import a prior-work seed using the configured provider")
    research_parser.add_argument("--output")
    research_parser.add_argument("--paper")
    research_parser.add_argument("--artifact-repo")
    research_parser.add_argument("--source", default="codex_web_seed")
    research_parser.add_argument("--import", dest="import_seed", action="store_true")
    research_parser.add_argument("--require-complete-metadata", action="store_true")
    add_runtime_mode_args(research_parser, strict_flag=True)
    add_common_provider_args(research_parser)

    import_parser = subparsers.add_parser("import-prior-work", help="Import a curated prior-work seed file")
    import_parser.add_argument("--seed-file", required=True)
    import_parser.add_argument("--source", default="manual_seed")
    import_parser.add_argument("--require-complete-metadata", action="store_true")

    sections_parser = subparsers.add_parser("write-sections", help="Draft or rewrite manuscript sections")
    sections_parser.add_argument("--only-sections")
    sections_parser.add_argument("--output-tex")
    sections_parser.add_argument("--claim-safe", action="store_true")
    sections_parser.add_argument(
        "--bypass-plan-gate",
        action="store_true",
        help="Explicitly bypass the paper-plan approval gate for legacy/manual runs",
    )
    add_runtime_mode_args(sections_parser, strict_flag=True)
    add_common_provider_args(sections_parser)

    critique_parser = subparsers.add_parser("critique", help="Run paper, section, and citation critics")
    critique_parser.add_argument("--source-paper")
    critique_parser.add_argument("--output-dir")
    critique_parser.add_argument("--citation-evidence-mode", default="heuristic", choices=["heuristic", "model", "web", "source"])
    critique_parser.add_argument("--live", action="store_true")
    critique_parser.add_argument("--claim-safe", action="store_true")
    add_runtime_mode_args(critique_parser, strict_flag=True)
    add_common_provider_args(critique_parser)

    run_parser = subparsers.add_parser("run", help="Run the full PaperOrchestra pipeline")
    run_parser.add_argument("--discovery-mode", default="model", choices=["model", "scholar-only", "search-grounded"])
    run_parser.add_argument("--verify-mode", default="live", choices=["live", "mock"])
    run_parser.add_argument("--verify-error-policy", default="skip", choices=["skip", "fail"])
    run_parser.add_argument("--verify-fallback-mode", default="none", choices=["none", "mock"])
    run_parser.add_argument("--require-live-verification", action="store_true")
    run_parser.add_argument("--refine-iterations", type=int, default=1)
    run_parser.add_argument("--compile", action="store_true")
    run_parser.add_argument(
        "--bypass-plan-gate",
        action="store_true",
        help="Explicitly bypass the paper-plan approval gate for legacy/manual runs",
    )
    add_runtime_mode_args(run_parser, strict_flag=True)
    add_common_provider_args(run_parser)
