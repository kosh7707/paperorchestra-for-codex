from __future__ import annotations

import pytest

from paperorchestra.cli import build_parser


MINIMAL_COMMANDS = {
    "init": [
        "init",
        "--idea",
        "idea.md",
        "--experimental-log",
        "experiment.md",
        "--template",
        "template.tex",
        "--guidelines",
        "guide.md",
    ],
    "status": ["status"],
    "inspect-state": ["inspect-state"],
    "orchestrate": ["orchestrate"],
    "answer-human-needed": ["answer-human-needed", "--answer", "approved"],
    "export-current": ["export-current", "--output", "out"],
    "research-prior-work": ["research-prior-work"],
    "import-prior-work": ["import-prior-work", "--seed-file", "seed.json"],
    "authoring-round": ["authoring-round"],
    "write-sections": ["write-sections"],
    "compile": ["compile"],
    "environment": ["environment"],
    "doctor": ["doctor"],
    "critique": ["critique"],
    "visual-audit": ["visual-audit"],
    "quality-gate": ["quality-gate"],
    "qa-loop": ["qa-loop"],
    "qa-loop-step": ["qa-loop-step"],
    "ralph-start": ["ralph-start"],
    "run": ["run"],
}


@pytest.mark.parametrize("command, argv", sorted(MINIMAL_COMMANDS.items()))
def test_public_commands_parse_minimal_arguments(command: str, argv: list[str]) -> None:
    args = build_parser().parse_args(argv)

    assert args.command == command


def test_authoring_round_flags_cover_first_draft_contract() -> None:
    args = build_parser().parse_args(
        [
            "authoring-round",
            "--round-dir",
            "round-1",
            "--require-web-research",
            "--require-live-critic",
            "--compile",
            "--citation-evidence-mode",
            "web",
            "--provider",
            "shell",
            "--provider-command",
            "codex --search exec",
            "--citation-provider",
            "shell",
            "--citation-provider-command",
            "codex --search exec",
        ]
    )

    assert args.command == "authoring-round"
    assert args.round_dir == "round-1"
    assert args.require_web_research is True
    assert args.require_live_critic is True
    assert args.compile is True
    assert args.citation_evidence_mode == "web"
    assert args.provider_command == "codex --search exec"
    assert args.citation_provider_command == "codex --search exec"


def test_provider_runtime_and_citation_flags_remain_on_quality_step() -> None:
    args = build_parser().parse_args(
        [
            "qa-loop-step",
            "--quality-mode",
            "claim_safe",
            "--max-iterations",
            "7",
            "--require-live-verification",
            "--accept-mixed-provenance",
            "--require-compile",
            "--citation-evidence-mode",
            "source",
            "--quality-eval",
            "quality.json",
            "--plan",
            "plan.json",
            "--citation-support-review",
            "citation.json",
            "--runtime-mode",
            "omx_native",
            "--strict-omx-native",
            "--provider",
            "mock",
            "--provider-command",
            "codex exec",
            "--citation-provider",
            "shell",
            "--citation-provider-command",
            "search cmd",
        ]
    )

    assert args.quality_mode == "claim_safe"
    assert args.max_iterations == 7
    assert args.require_live_verification is True
    assert args.accept_mixed_provenance is True
    assert args.require_compile is True
    assert args.citation_evidence_mode == "source"
    assert args.quality_eval == "quality.json"
    assert args.plan == "plan.json"
    assert args.citation_support_review == "citation.json"
    assert args.runtime_mode == "omx_native"
    assert args.strict_omx_native is True
    assert args.provider == "mock"
    assert args.provider_command == "codex exec"
    assert args.citation_provider == "shell"
    assert args.citation_provider_command == "search cmd"


def test_visual_audit_flags_cover_render_and_imported_findings_contract() -> None:
    args = build_parser().parse_args(
        [
            "visual-audit",
            "--pdf",
            "compiled.pdf",
            "--output",
            "page-layout-review.json",
            "--render-dir",
            "rendered-pages",
            "--findings-json",
            "page-visual-findings.json",
        ]
    )

    assert args.command == "visual-audit"
    assert args.pdf == "compiled.pdf"
    assert args.output == "page-layout-review.json"
    assert args.render_dir == "rendered-pages"
    assert args.findings_json == "page-visual-findings.json"


def test_draft_generating_commands_require_explicit_plan_gate_bypass_flag() -> None:
    parser = build_parser()

    write_args = parser.parse_args(["write-sections", "--bypass-plan-gate"])
    run_args = parser.parse_args(["run", "--bypass-plan-gate"])

    assert write_args.bypass_plan_gate is True
    assert run_args.bypass_plan_gate is True


def test_ralph_start_launch_mode_is_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["ralph-start", "--dry-run", "--launch"])

    assert excinfo.value.code == 2
