import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
PAPERO_SKILLS = sorted(path.parent.name for path in SKILLS.glob("paperorchestra*/SKILL.md"))
PAPERO_CLI = ROOT / ".venv" / "bin" / "paperorchestra"
CLI = str(PAPERO_CLI if PAPERO_CLI.exists() else "paperorchestra")


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def assert_mentions(skill: str, *tokens: str) -> None:
    text = skill_text(skill)
    missing = [token for token in tokens if token not in text]
    assert not missing, f"{skill} missing required mock/workflow tokens: {missing}"


def run_cmd(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )


def write_minimal_session(tmp_path: Path) -> Path:
    workspace = tmp_path / "mock-paper"
    workspace.mkdir()
    idea = workspace / "idea.md"
    log = workspace / "experimental-log.md"
    template = workspace / "template.tex"
    guidelines = workspace / "guidelines.md"
    idea.write_text(
        "# Mock paper idea\nA synthetic pipeline paper about reducing false positives in alerts.\n",
        encoding="utf-8",
    )
    log.write_text(
        "# Mock experimental log\nPrecision is a placeholder. No real project material is used.\n",
        encoding="utf-8",
    )
    template.write_text(
        "\\documentclass{article}\n\\begin{document}\nPlaceholder.\\end{document}\n",
        encoding="utf-8",
    )
    guidelines.write_text("Use concise article format.\n", encoding="utf-8")
    init = run_cmd(
        [
            CLI,
            "init",
            "--idea",
            str(idea),
            "--experimental-log",
            str(log),
            "--template",
            str(template),
            "--guidelines",
            str(guidelines),
            "--venue",
            "MockVenue",
            "--page-limit",
            "4",
        ],
        workspace,
    )
    assert init.returncode == 0, init.stderr or init.stdout
    return workspace


def test_every_paperorchestra_skill_has_mock_or_contract_coverage() -> None:
    assert PAPERO_SKILLS == [
        "paperorchestra",
        "paperorchestra-authoring-round",
        "paperorchestra-figure",
        "paperorchestra-intake",
        "paperorchestra-live-review",
        "paperorchestra-plan",
        "paperorchestra-quality-gate",
        "paperorchestra-research-swarm",
        "paperorchestra-setup",
        "paperorchestra-status",
        "paperorchestra-visual-audit",
    ]


# One contract test per skill. These are the mock equivalents of invoking the skill:
# they assert each skill points at safe mock/fallback surfaces and refuses unsafe live shortcuts.

def test_router_mock_contract() -> None:
    assert_mentions(
        "paperorchestra",
        "paperorchestra run --provider mock --verify-mode mock --runtime-mode compatibility",
        "paperorchestra quality-gate --quality-mode claim_safe",
        "$paperorchestra-research-swarm",
        "If the next action is `start_autoresearch` / `$autoresearch`",
    )


def test_setup_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-setup",
        "paperorchestra --help",
        "paperorchestra environment",
        "paperorchestra doctor",
        "mock",
        "MCP attachment",
    )


def test_status_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-status",
        "paperorchestra status --json",
        "paperorchestra environment",
        "Recommended next round",
        "$paperorchestra-research-swarm + $ultrawork + $autoresearch",
    )


def test_intake_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-intake",
        "$deep-interview",
        "Do **not** write `paper-intake.md`, `paper-plan.md`, `paper-skeleton.md`, or manuscript files yet",
        "Do not start `$paperorchestra-research-swarm`",
    )


def test_plan_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-plan",
        "paper-plan.md v3",
        "$ralplan",
        "$paperorchestra-research-swarm",
        "Stop when `paper-plan.md` exists",
    )


def test_research_swarm_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-research-swarm",
        "$ultrawork",
        "$team",
        "agent_type=researcher",
        "agent_type=verifier",
        "$autoresearch",
        "result.json` records `passed: true`",
        "paperorchestra research-prior-work --import",
    )


def test_authoring_round_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-authoring-round",
        "Use mock providers or `--citation-evidence-mode heuristic` only for explicit local smoke tests",
        "paperorchestra research-prior-work",
        "paperorchestra authoring-round --provider shell",
        "paperorchestra write-sections",
        "paperorchestra critique",
        "$paperorchestra-research-swarm",
    )


def test_figure_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-figure",
        "paperorchestra visual-audit",
        "deterministic source-of-truth",
        "output-form gate",
        "imagegen",
        "prompt only / no image generated",
        "$visual-verdict",
    )


def test_visual_audit_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-visual-audit",
        "Do not assume the installed CLI exposes `paperorchestra visual-audit`",
        "$visual-verdict",
        "page-layout-review.json",
        "visual_repair_brief.json",
    )


def test_live_review_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-live-review",
        "paperorchestra critique",
        "--provider shell",
        "--citation-evidence-mode web",
        "mock_smoke",
        "$paperorchestra-research-swarm",
    )


def test_quality_gate_mock_contract() -> None:
    assert_mentions(
        "paperorchestra-quality-gate",
        "paperorchestra critique --provider shell --provider-command \"$PAPERO_MODEL_CMD\" --citation-evidence-mode web",
        "paperorchestra quality-gate --quality-mode claim_safe",
        "paperorchestra qa-loop --quality-mode claim_safe",
        "paperorchestra qa-loop-step --quality-mode claim_safe --max-iterations 1",
        "$paperorchestra-research-swarm",
    )


def test_installed_cli_help_supports_mock_fallback_commands() -> None:
    commands = {
        "init": ["--idea", "IDEA"],
        "status": ["--json"],
        "environment": [],
        "doctor": [],
        "run": ["--provider", "mock", "--verify-mode", "mock"],
        "research-prior-work": ["--provider", "mock", "--import"],
        "import-prior-work": ["--seed-file"],
        "authoring-round": ["--provider", "mock", "--citation-evidence-mode"],
        "write-sections": ["--provider", "mock"],
        "critique": ["--provider", "mock", "--citation-evidence-mode"],
        "visual-audit": ["--require-ai-artifact-check", "--require-publication-figure-check"],
        "quality-gate": ["--quality-mode", "claim_safe"],
        "qa-loop": ["--quality-mode", "claim_safe"],
        "qa-loop-step": ["--provider", "mock", "--citation-evidence-mode", "heuristic"],
        "compile": [],
        "approve-plan": ["--approved-by", "--json"],
        "export-current": ["--output", "--json"],
        "inspect-state": ["--json"],
        "orchestrate": ["--execute-local", "--json"],
        "answer-human-needed": ["--answer", "--apply"],
        "ralph-start": ["--dry-run", "--launch"],
    }
    for command, tokens in commands.items():
        result = run_cmd([CLI, command, "--help"], ROOT)
        assert result.returncode == 0, f"{command} --help failed: {result.stderr or result.stdout}"
        help_text = result.stdout + result.stderr
        for token in tokens:
            assert token in help_text, f"{command} --help missing {token!r}"


def test_mock_session_status_and_core_diagnostic_commands_do_not_need_real_project(tmp_path: Path) -> None:
    workspace = write_minimal_session(tmp_path)
    status = run_cmd([CLI, "status", "--json"], workspace)
    assert status.returncode == 0, status.stderr or status.stdout
    data = json.loads(status.stdout)
    assert data.get("session_id") or data.get("initialized") is not None

    env = run_cmd([CLI, "environment"], workspace)
    assert env.returncode == 0, env.stderr or env.stdout

    inspect = run_cmd([CLI, "inspect-state", "--json"], workspace)
    assert inspect.returncode == 0, inspect.stderr or inspect.stdout
    inspect_data = json.loads(inspect.stdout)
    assert inspect_data.get("session_id") == data.get("session_id")
