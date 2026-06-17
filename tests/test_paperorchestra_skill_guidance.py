from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


EXPECTED_SKILLS = [
    "paperorchestra",
    "paperorchestra-status",
    "paperorchestra-setup",
    "paperorchestra-live-review",
    "paperorchestra-quality-gate",
    "paperorchestra-authoring-round",
]


class PaperOrchestraSkillGuidanceTests(unittest.TestCase):
    def _readme(self) -> str:
        return Path("README.md").read_text(encoding="utf-8")

    def _environment(self) -> str:
        return Path("ENVIRONMENT.md").read_text(encoding="utf-8")

    def _skill(self, name: str = "paperorchestra") -> str:
        return Path("skills") .joinpath(name, "SKILL.md").read_text(encoding="utf-8")

    def test_all_operational_skills_exist_with_matching_frontmatter(self) -> None:
        for name in EXPECTED_SKILLS:
            with self.subTest(skill=name):
                path = Path("skills") / name / "SKILL.md"
                self.assertTrue(path.exists(), f"missing {path}")
                text = path.read_text(encoding="utf-8")
                self.assertIn(f"name: {name}", text)
                self.assertIn("description:", text)
                self.assertNotIn("TODO", text)

    def test_router_skill_routes_first_use_to_specific_operational_skills(self) -> None:
        text = self._skill("paperorchestra")
        for phrase in [
            "first_use_guide",
            "inspect_state",
            "orchestrate",
            "continue_project",
            "answer_human_needed",
            "export_results",
            "Do not dump README",
            "insufficient material",
            "blocks drafting",
            "registration",
            "active attachment",
            "execute_local",
            "one deterministic local step",
            "not a full pipeline",
            "Execution status",
            "next action",
            "machine-solvable citation/search",
            "start_autoresearch",
            "$autoresearch",
            "reject unsafe drafting",
            "paperorchestra first-use",
        ]:
            self.assertIn(phrase, text)
        for skill in EXPECTED_SKILLS[1:]:
            self.assertIn(f"${skill}", text)

    def test_status_skill_is_state_card_and_round_advisor(self) -> None:
        text = self._skill("paperorchestra-status")
        for phrase in [
            "status card",
            "Materials",
            "Current trust",
            "Latest artifacts",
            "Recommended next round",
            "setup needed",
            "live-review recommended",
            "quality-gate recommended",
            "authoring-round recommended",
            "human-needed answer required",
            "materials missing",
            "stale",
            "manuscript hash",
        ]:
            self.assertIn(phrase, text)

    def test_setup_skill_covers_preflight_without_requiring_s2(self) -> None:
        text = self._skill("paperorchestra-setup")
        for phrase in [
            "paperorchestra doctor",
            "paperorchestra environment",
            "paperorchestra status --json",
            "paperorchestra critic-preflight",
            "PAPERO_MODEL_CMD",
            "S2 API key is optional",
            "mock",
            "heuristic",
            "shell-live",
            "claim-safe-live",
        ]:
            self.assertIn(phrase, text)

    def test_live_review_skill_cannot_silently_use_mock_or_heuristic(self) -> None:
        text = self._skill("paperorchestra-live-review")
        for phrase in [
            "critic-preflight --live",
            "critique --live",
            "review-citations --evidence-mode web",
            "progress JSONL",
            "mock_smoke",
            "local_diagnostic",
            "heuristic_citation",
            "live_model_review",
            "web_citation_review",
            "claim_safe_live",
            "never claim live",
        ]:
            self.assertIn(phrase, text)

    def test_quality_gate_skill_is_bounded_and_preserves_human_needed(self) -> None:
        text = self._skill("paperorchestra-quality-gate")
        for phrase in [
            "validate-current",
            "build-source-obligations",
            "compile",
            "review-citations --evidence-mode web",
            "quality-eval --quality-mode",
            "qa-loop-plan",
            "qa-loop-step",
            "bounded",
            "human_needed",
            "failed",
            "ready_for_human_finalization",
            "not submission-ready",
        ]:
            self.assertIn(phrase, text)

    def test_authoring_round_skill_composes_review_gate_and_edit_artifacts(self) -> None:
        text = self._skill("paperorchestra-authoring-round")
        for phrase in [
            "$paperorchestra-status",
            "$paperorchestra-live-review",
            "$paperorchestra-quality-gate",
            "round directory",
            "only if the user asked for edits",
            "compile/validate",
            "artifact manifest",
            "do not edit on human_needed",
        ]:
            self.assertIn(phrase, text)

    def test_readme_is_short_router_for_skills_not_full_runbook(self) -> None:
        text = self._readme()
        self.assertLessEqual(len(text.splitlines()), 450)
        self.assertIn("## Skill-first workflow", text)
        self.assertIn("## Tutorials", text)
        for skill in EXPECTED_SKILLS:
            self.assertIn(f"${skill}", text)
        for phrase in [
            "v1-alpha",
            "not submission-ready",
            "known limitations",
            "citation/claim quality",
            "figure finalization",
            "operator repair convergence",
            "false readiness",
            "diagnostic artifact",
            "not a readiness pass",
        ]:
            self.assertIn(phrase, text)

    def test_install_script_copies_all_repository_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            subprocess.run(["bash", "scripts/install-skill.sh", str(target)], check=True, cwd=Path.cwd())
            for skill in EXPECTED_SKILLS:
                with self.subTest(skill=skill):
                    self.assertTrue((target / skill / "SKILL.md").exists())


    def test_root_installer_supports_clone_and_go_dry_run(self) -> None:
        installer = Path("install.sh")
        self.assertTrue(installer.exists(), "missing root install.sh")
        self.assertTrue(installer.stat().st_mode & 0o111, "install.sh must be executable")
        result = subprocess.run(
            ["bash", "install.sh", "--dry-run"],
            cwd=Path.cwd(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        output = result.stdout
        for phrase in [
            "PaperOrchestra installer",
            "python -m venv .venv",
            "pip install",
            "scripts/install-skill.sh",
            "scripts/register-codex-mcp.sh --use-local-venv",
            "PAPERO_MODEL_CMD",
            '["codex","--search","exec","--skip-git-repo-check"]',
            "Next:",
            ".venv/bin/paperorchestra status --json",
        ]:
            self.assertIn(phrase, output)
        self.assertNotIn("scripts/demo-mock.sh --in-repo", output)
        self.assertNotIn("gpt-5.5", output)
        self.assertNotIn("model_reasoning_effort", output)

    def test_readme_installation_is_clone_install_not_manual_pip_recipe(self) -> None:
        text = self._readme()
        install_section = text.split("## Skill-first workflow", 1)[0]
        self.assertIn("## Installation", install_section)
        self.assertNotIn("TL;DR", install_section)
        self.assertIn("git clone", install_section)
        self.assertIn("cd paperorchestra-for-codex && ./install.sh", install_section)
        self.assertNotIn("./install.sh --demo", install_section)
        self.assertNotIn("./install.sh --mcp", install_section)
        self.assertNotIn("pip install -e", install_section)
        self.assertNotIn("python -m venv", install_section)
        self.assertNotIn(". .venv/bin/activate", install_section)
        self.assertNotIn("export PAPERO_MODEL_CMD", install_section)

    def test_readme_removes_noisy_quick_paths(self) -> None:
        text = self._readme()
        for phrase in [
            "Codex-first setup path",
            "No-live local-step check",
            "Minimal first run",
            "Real-review quick path",
            "Quality gate quick path",
            "export PAPERO_MODEL_CMD",
            "gpt-5.5",
            "model_reasoning_effort",
        ]:
            self.assertNotIn(phrase, text)

    def test_environment_mentions_no_live_local_step_check(self) -> None:
        text = self._environment()
        self.assertIn("no-live local-step check", text)
        self.assertIn("--execute-local", text)
        self.assertIn("execute_local", text)
