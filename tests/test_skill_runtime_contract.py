import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def all_skill_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SKILLS.glob("paperorchestra*/SKILL.md"))


def assert_mentions(skill: str, *tokens: str) -> None:
    text = skill_text(skill)
    missing = [token for token in tokens if token not in text]
    assert not missing, f"{skill} missing required tokens: {missing}"


def test_skills_do_not_document_stale_cli_commands() -> None:
    text = all_skill_text()
    stale = [
        "paperorchestra environment --summary",
    ]
    missing = [token for token in stale if token in text]
    assert not missing, f"Stale/unsupported CLI snippets remain: {missing}"


def test_cli_fallbacks_use_current_command_surface() -> None:
    assert_mentions(
        "paperorchestra",
        "paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility",
        "paperorchestra quality-eval --quality-mode claim_safe",
        "paperorchestra qa-loop-plan --quality-mode claim_safe",
        "paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1",
    )
    assert_mentions(
        "paperorchestra-authoring-round",
        "For MCP/source-checkout execution",
        "python -m paperorchestra.cli authoring-round",
        "paperorchestra authoring-round --help",
        "If it fails, use the staged fallback",
        "paperorchestra research-prior-work",
        "paperorchestra plan-narrative",
        "paperorchestra write-sections",
        "paperorchestra critique",
    )
    assert_mentions(
        "paperorchestra-quality-gate",
        "Preferred MCP/source gate",
        "Installed CLI fallback",
        "paperorchestra validate-current",
        "paperorchestra quality-eval --quality-mode claim_safe",
        "paperorchestra qa-loop-plan --quality-mode claim_safe",
    )
    assert_mentions(
        "paperorchestra-live-review",
        "Installed CLI fallback may not expose `--live`",
        "If `paperorchestra critique --help` shows `--live`, include it",
    )


def test_fresh_start_boundary_blocks_prior_context_reuse() -> None:
    for skill in ["paperorchestra", "paperorchestra-status", "paperorchestra-intake"]:
        assert_mentions(
            skill,
            "Fresh-start boundary",
            "explicitly requests a fresh start",
            "context reset",
            "do not reuse prior project paths",
            "ask for the material path again",
        )
        assert "처음 보는 사이" not in skill_text(skill)
        assert "처음부터" not in skill_text(skill)


def test_setup_and_status_use_current_environment_command() -> None:
    assert_mentions(
        "paperorchestra-setup",
        "command -v paperorchestra",
        "command -v paperorchestra-mcp",
        "paperorchestra --help",
        "paperorchestra environment",
        "paperorchestra doctor",
        "paperorchestra_mcp_health",
        "binary.exists",
        "server.ok",
        "active_session_attachment",
        "registered MCP command",
        ".venv/bin/paperorchestra",
        ".venv/bin/paperorchestra-mcp",
        "scripts/check-cli-surface.py",
        "--strict-installed",
        "python3 -m paperorchestra.cli --help",
        "PYTHONPATH=<checkout> python3 -m paperorchestra.cli <command>",
        "command-surface mismatch",
    )
    assert_mentions(
        "paperorchestra-status",
        "paperorchestra environment",
        "quality-gate.report.json",
    )
    assert "environment --summary" not in skill_text("paperorchestra-setup")
    assert "environment --summary" not in skill_text("paperorchestra-status")


def test_installed_skill_contract_matches_fresh_session_expectations(tmp_path: Path) -> None:
    target = tmp_path / "skills"

    subprocess.run(
        [str(ROOT / "scripts" / "install-skill.sh"), str(target)],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    installed_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in target.glob("paperorchestra*/SKILL.md")
    )
    assert "paperorchestra environment --summary" not in installed_text
    assert (target / "paperorchestra" / "references" / "academic-writing.md").exists()
    for skill in ["paperorchestra", "paperorchestra-status", "paperorchestra-intake"]:
        body = (target / skill / "SKILL.md").read_text(encoding="utf-8")
        assert "Fresh-start boundary" in body
        assert "do not reuse prior project paths" in body
        assert "ask for the material path again" in body


def test_documented_installed_cli_fallback_commands_have_help() -> None:
    commands = [
        "status",
        "environment",
        "critique",
        "quality-eval",
        "qa-loop-plan",
        "qa-loop-step",
        "validate-current",
        "plan-narrative",
        "research-prior-work",
        "write-sections",
    ]
    for command in commands:
        result = subprocess.run(
            ["paperorchestra", command, "--help"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def test_source_checkout_specific_commands_are_caveated() -> None:
    source_help = subprocess.run(
        ["python3", "-m", "paperorchestra.cli", "--help"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    installed_help = subprocess.run(
        ["paperorchestra", "--help"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    if source_help != installed_help:
        assert_mentions(
            "paperorchestra-setup",
            "python3 -m paperorchestra.cli --help",
            "command-surface mismatch",
        )
        assert_mentions(
            "paperorchestra-authoring-round",
            "For MCP/source-checkout execution",
            "installed CLI fallback",
        )
        assert_mentions(
            "paperorchestra-live-review",
            "Installed CLI fallback may not expose `--live`",
        )
        assert_mentions(
            "paperorchestra-quality-gate",
            "Preferred MCP/source gate",
            "Installed CLI fallback",
        )
