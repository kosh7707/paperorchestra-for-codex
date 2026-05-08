from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


class PreLiveCheckScriptTests(unittest.TestCase):
    def _extract_release_safety_scan_python(self) -> str:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        function_start = wrapper.index("run_release_safety_scan() {")
        heredoc_start = wrapper.index("python3 - \"$scan_root\" \"$output\" <<'PY_RELEASE_SCAN'", function_start)
        python_start = wrapper.index("\n", heredoc_start) + 1
        python_end = wrapper.index("\nPY_RELEASE_SCAN\n}", python_start)
        return wrapper[python_start:python_end]

    def _extract_scan_meta_leakage_python(self) -> str:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        function_start = wrapper.index("scan_meta_leakage() {")
        heredoc_start = wrapper.index("python3 - \"$ARTIFACTS\" <<'PY'", function_start)
        python_start = wrapper.index("\n", heredoc_start) + 1
        python_end = wrapper.index("\nPY\n}", python_start)
        return wrapper[python_start:python_end]

    def test_pre_live_check_script_is_syntax_valid_and_secret_safe(self) -> None:
        path = Path("scripts/pre-live-check.sh")
        self.assertTrue(path.exists())
        self.assertTrue(path.stat().st_mode & 0o111)
        subprocess.run(["bash", "-n", str(path)], check=True)
        text = path.read_text(encoding="utf-8")
        self.assertIn("tests.test_s2_api", text)
        for group in [
            "environment_docs",
            "provider_runtime",
            "s2_wrapper",
            "literature_discovery",
            "live_verification",
            "source_planning",
            "validation_review",
            "quality_loop",
            "omx_ralph_integration",
            "eval_surfaces",
            "guided_intake",
            "prompt_fidelity",
            "citation_session",
        ]:
            self.assertIn(f"run_unittest_group {group}", text)
        self.assertIn("strict_smoke_policy", text)
        self.assertIn("test_verify_papers_live_success_uses_s2_metadata_and_citation_map", text)
        self.assertIn("omx_runtime_probe", text)
        self.assertIn("omx ralph --help", text)
        self.assertIn("test_ralph_start_launch_calls_omx_ralph_explicitly", text)
        self.assertIn("test_omx_exec_sends_large_prompt_over_stdin_not_argv", text)
        self.assertIn("test_qa_loop_step_runs_tier0_precondition_refresh_handlers", text)
        self.assertIn("env -u PAPERO_STRICT_CONTENT_GATES", text)
        self.assertIn("FEATURE_MATRIX.md", text)
        self.assertIn("--live-s2", text)
        self.assertNotIn("s2" "k-", text)
        self.assertNotRegex(text, r"echo .*\$\{?SEMANTIC_SCHOLAR_API_KEY")


    def test_demo_mock_uses_throwaway_workdir_without_deleting_repo_session(self) -> None:
        text = Path("scripts/demo-mock.sh").read_text(encoding="utf-8")

        self.assertIn("PAPERO_DEMO_WORKDIR", text)
        self.assertIn("--allow-outside-workspace", text)
        self.assertIn("python3 -m paperorchestra.cli", text)
        self.assertIn("PAPERO_CMD_OVERRIDE", text)
        self.assertNotIn("command -v paperorchestra", text)
        self.assertNotIn("rm -rf .paper-orchestra", text)

    def test_demo_mock_ignores_stale_global_paperorchestra_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            marker = root / "stale-global-used.txt"
            fake = fake_bin / "paperorchestra"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                f"echo stale-global > {str(marker)!r}\n"
                "exit 99\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            workdir = root / "demo"
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
            env["PAPERO_DEMO_WORKDIR"] = str(workdir)
            env["PAPERO_DEMO_KEEP_WORKDIR"] = "1"

            result = subprocess.run(
                ["bash", "scripts/demo-mock.sh"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            self.assertFalse(marker.exists())
            self.assertTrue((workdir / ".paper-orchestra" / "current_session.txt").exists())

    def test_register_codex_mcp_script_updates_toml_idempotently(self) -> None:
        path = Path("scripts/register-codex-mcp.sh")
        self.assertTrue(path.exists())
        self.assertTrue(path.stat().st_mode & 0o111)
        subprocess.run(["bash", "-n", str(path)], check=True)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.toml"
            command = root / "paperorchestra-mcp"
            command.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            command.chmod(0o755)
            config.write_text(
                "[profiles.default]\n"
                'model = "gpt-5.5"\n'
                "\n"
                "[mcp_servers.paperorchestra]\n"
                'command = "stale-paperorchestra-mcp"\n'
                "\n"
                "[mcp_servers.paperorchestra.env]\n"
                'PAPERO_ALLOWED_PROVIDER_BINARIES = "stale"\n',
                encoding="utf-8",
            )

            for _ in range(2):
                result = subprocess.run(
                    [
                        "bash",
                        str(path),
                        "--config",
                        str(config),
                        "--command",
                        str(command),
                        "--allowed-provider-binaries",
                        "codex,omx",
                        "--startup-timeout-sec",
                        "12",
                        "--no-backup",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            text = config.read_text(encoding="utf-8")
            tomllib.loads(text)
            self.assertIn("[profiles.default]", text)
            self.assertEqual(text.count("[mcp_servers.paperorchestra]"), 1)
            self.assertEqual(text.count("[mcp_servers.paperorchestra.env]"), 1)
            self.assertIn(f'command = "{command}"', text)
            self.assertIn("enabled = true", text)
            self.assertIn("startup_timeout_sec = 12", text)
            self.assertIn('PAPERO_ALLOWED_PROVIDER_BINARIES = "codex,omx"', text)
            self.assertNotIn("stale-paperorchestra-mcp", text)

    def test_register_codex_mcp_dry_run_does_not_write_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "missing" / "config.toml"

            result = subprocess.run(
                [
                    "bash",
                    "scripts/register-codex-mcp.sh",
                    "--config",
                    str(config),
                    "--command",
                    str(root / "paperorchestra-mcp"),
                    "--dry-run",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(config.exists())
            self.assertIn("[mcp_servers.paperorchestra]", result.stdout)
            self.assertIn("[dry-run] would write Codex MCP config", result.stderr)

    def test_register_codex_mcp_backs_up_existing_config_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.toml"
            config.write_text("[profiles.default]\n", encoding="utf-8")

            result = subprocess.run(
                [
                    "bash",
                    "scripts/register-codex-mcp.sh",
                    "--config",
                    str(config),
                    "--command",
                    str(root / "paperorchestra-mcp"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list(root.glob("config.toml.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "[profiles.default]\n")
            self.assertIn("Backed up existing config to:", result.stderr)

    def test_setup_codex_mcp_delegates_codex_cli_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "codex" / "config.toml"
            command = root / "paperorchestra-mcp"
            command.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            command.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    "scripts/setup-codex-mcp.sh",
                    "--codex-cli",
                    "--config",
                    str(config),
                    "--command",
                    str(command),
                    "--no-backup",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            text = config.read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.paperorchestra]", text)
            self.assertIn(f'command = "{command}"', text)

    def test_paperorchestra_mcp_smoke_script_checks_stdio_server_health(self) -> None:
        path = Path("scripts/smoke-paperorchestra-mcp.py")
        self.assertTrue(path.exists())
        self.assertTrue(path.stat().st_mode & 0o111)
        subprocess.run([sys.executable, "-m", "py_compile", str(path), "paperorchestra/mcp_smoke.py"], check=True)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.toml"
            config.write_text(
                "[mcp_servers.paperorchestra]\n"
                f"command = {json.dumps(sys.executable)}\n"
                f"args = {json.dumps(['-m', 'paperorchestra.mcp_server'])}\n"
                "enabled = true\n"
                "\n"
                "[mcp_servers.paperorchestra.env]\n"
                f"PYTHONPATH = {json.dumps(str(Path.cwd()))}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(path),
                    "--config",
                    str(config),
                    "--cwd",
                    str(root),
                    "--json",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["config"]["registered"])
        self.assertTrue(payload["server"]["initialize_ok"])
        self.assertTrue(payload["server"]["tools_list_ok"])
        self.assertGreaterEqual(payload["server"]["tool_count"], 50)
        self.assertTrue(payload["server"]["expected_tools_present"])
        self.assertTrue(payload["server"]["status_call_reached_server"])
        self.assertFalse(payload["active_session_attachment"]["checked"])

    def test_register_codex_mcp_script_explains_registration_vs_active_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.toml"
            command = root / "paperorchestra-mcp"
            command.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            command.chmod(0o755)

            result = subprocess.run(
                [
                    "bash",
                    "scripts/register-codex-mcp.sh",
                    "--config",
                    str(config),
                    "--command",
                    str(command),
                    "--no-backup",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mcp__paperorchestra__status", result.stderr)
        self.assertIn("scripts/smoke-paperorchestra-mcp.py", result.stderr)
        self.assertIn("config registration, not active session attachment", result.stderr)

    def test_strict_smoke_policy_script_exists_and_runs_full_claim_safe_stack(self) -> None:
        path = Path("scripts/live-smoke-claim-safe.sh")
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        self.assertTrue(path.exists())
        self.assertTrue(wrapper.exists())
        self.assertTrue(wrapper.stat().st_mode & 0o111)
        self.assertTrue(path.stat().st_mode & 0o111)
        subprocess.run(["bash", "-n", str(path), str(wrapper)], check=True)
        live_text = path.read_text(encoding="utf-8")
        wrapper_text = wrapper.read_text(encoding="utf-8")
        text = live_text + "\n" + wrapper_text
        for token in [
            "validate-current",
            "build-source-obligations",
            "compile",
            "review --runtime-mode omx_native --strict-omx-native",
            "review-sections",
            "review-figure-placement",
            "review-citations --evidence-mode web",
            'quality-eval --quality-mode claim_safe --max-iterations "$MAX_ITERATIONS" --require-live-verification',
            'qa-loop-plan --quality-mode claim_safe --max-iterations "$MAX_ITERATIONS" --require-live-verification',
            "qa-loop-step",
            "validate-claim-safe-current",
            "--require-compile",
            "--citation-evidence-mode web",
            "final-verdict.txt",
            "exitcode",
            "stdout.log",
            "stderr.log",
            "qa-loop-execution.iter-*.json",
            "paper.citation-repair.candidate.tex",
            "validation.claim-safe-current.json",
            "fresh-smoke-verdict/1",
            "pass_loop_verified",
            "fail_material_invariance",
            "validate-fresh-smoke-materials.py",
            "validate-fresh-smoke-evidence.py",
            "build-operator-review-packet",
            "import-operator-feedback",
            "apply-operator-feedback",
            "operator_feedback.execution.cycle-${cycle}.json",
            "operator_feedback_cycles_attempted",
            "operator_feedback_cycles_promoted",
            "operator_feedback_cycles_rolled_back",
            "operator_feedback_cycles_failed",
            "Verdict transition protocol",
            "capture-time holding",
            "seed_only_count",
            "live_coverage_ratio",
            "provenance_level",
        ]:
            self.assertIn(token, text)
        for wrapper_token in [
            "scripts/validate-fresh-smoke-materials.py",
            "scripts/validate-fresh-smoke-evidence.py",
            'python3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py"',
            "fresh-smoke-verdict/1",
            "fail_critic_reject",
            "final-smoke-exit-code.txt",
            "build-operator-review-packet",
            "import-operator-feedback",
            "apply-operator-feedback",
        ]:
            self.assertIn(wrapper_token, wrapper_text)
        self.assertIn('case "$FINAL" in', wrapper_text)
        self.assertEqual(wrapper_text.count('python3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py"'), 4)
        self.assertNotIn('scripts/validate-fresh-smoke-evidence.py "$EVIDENCE_ROOT"', wrapper_text)
        self.assertIn('max_iterations_exhausted_with_continue', wrapper_text)
        self.assertIn('evidence_completeness_pre_critic', wrapper_text)
        self.assertIn('build_fresh_smoke_artifact_manifest', wrapper_text)
        self.assertIn('make_manifest\npython3 "$REPO_ROOT/scripts/validate-fresh-smoke-evidence.py"', wrapper_text)
        self.assertIn('PAPERO_SMOKE_COMMAND_NAME', wrapper_text)
        self.assertIn('provider-trace-meta/1', wrapper_text)
        self.assertIn('PAPERO_SMOKE_CODEX_HOME', wrapper_text)
        self.assertIn('rm -f "$SMOKE_CODEX_HOME/hooks.json"', wrapper_text)
        self.assertIn('CODEX_HOME="$SMOKE_CODEX_HOME" codex exec', wrapper_text)
        self.assertIn('if [[ -f "$candidate_artifact" ]]; then', text)
        self.assertIn('printf \'%s\\n\' "$STEP_RC" >"$EVIDENCE_ROOT/final-exit-code.txt"', text)
        self.assertIn('cp "${current_artifacts}/${artifact}" "$EVIDENCE_ROOT/artifacts/${artifact}"', text)
        self.assertIn("refresh_session_artifacts()", text)
        self.assertIn('json_sources = sorted(path for path in artifact_dir.rglob("*.json")', text)
        self.assertIn('"referenced_by": f"artifacts/{artifact_json.relative_to(artifact_dir)}"', text)
        validate_idx = text.index("run_step validate_claim_safe_current")
        refresh_after_validate_idx = text.index("post-step policy state", validate_idx)
        plan_read_idx = text.index('if [[ -f "$EVIDENCE_ROOT/artifacts/qa-loop.plan.json" ]]')
        self.assertLess(validate_idx, refresh_after_validate_idx)
        self.assertLess(refresh_after_validate_idx, plan_read_idx)
        self.assertIn("qa_loop_step_verdict", text)
        self.assertIn("post_step_plan_verdict", text)
        self.assertIn("operators should treat the refreshed post-step plan as the current quality-loop policy state", text)
        self.assertIn("Interpretation: qa_loop_step_verdict is the direct semantic exit", text)
        self.assertNotIn("Interpretation: `qa_loop_step_verdict`", text)
        self.assertIn("export PAPERO_PROVIDER_RETRY_ATTEMPTS=0", wrapper_text)
        self.assertIn("export PAPERO_PROVIDER_RETRY_SAFE=0", wrapper_text)
        self.assertIn("export PAPERO_OMX_RETRY_ATTEMPTS=0", wrapper_text)
        self.assertNotIn('PAPERO_PROVIDER_RETRY_ATTEMPTS="${PAPERO_PROVIDER_RETRY_ATTEMPTS:-0}"', wrapper_text)
        self.assertIn("PAPERO_CODEX_RETRY_ATTEMPTS", wrapper_text)
        self.assertIn("python3 -m paperorchestra.transport_retry --file", wrapper_text)
        self.assertNotIn("grep -Eiq 'Reconnecting", wrapper_text)
        self.assertIn("[REDACTED_PRIVATE_ARTIFACT_PATH]", wrapper_text)
        self.assertIn('redact < "$raw_attempt_stderr" > "$attempt_stderr"', wrapper_text)
        self.assertIn('run_step release_safety_scan_final run_release_safety_scan', wrapper_text)
        self.assertIn("run_without_papero_env", wrapper_text)
        self.assertIn("run_step unittest bash -c 'run_without_papero_env", wrapper_text)
        self.assertIn("run_step pre_live_all bash -c 'run_without_papero_env", wrapper_text)
        self.assertIn(r"((supplied|provided) (material|source|file|analysis|analyses|log|evidence|theorem statements?)|available (material|source|file|log))", wrapper_text)
        self.assertIn(r"(following|specified in|as specified in) the packet", wrapper_text)
        self.assertIn("SYSTEM_TEST_VERDICT: PASS", wrapper_text)
        self.assertIn("critic_rejected", wrapper_text)
        self.assertIn("current_qa_plan_verdict()", wrapper_text)
        self.assertIn("iteration_budget_exhausted_after_operator_feedback", wrapper_text)
        current_plan_idx = wrapper_text.index('current_plan_verdict="$(current_qa_plan_verdict)"')
        operator_increment_idx = wrapper_text.index('OPERATOR_FEEDBACK_CYCLES=$((OPERATOR_FEEDBACK_CYCLES + 1))')
        self.assertLess(current_plan_idx, operator_increment_idx)
        self.assertIn('tier_status.get("tier_3_scholarly_quality") != "pass"', wrapper_text)
        self.assertIn('quality_gate = "fail_provenance"', wrapper_text)
        self.assertNotIn('{"pass", "skipped", "skipped_due_to_upstream_fail"}', wrapper_text)
        self.assertIn(
            'copy_session_artifacts\n[[ -f "$ARTIFACTS/qa-loop.plan.final.json" ]] && reconcile_final_qa_plan_with_terminal_state || true\nscan_meta_leakage',
            wrapper_text,
        )
        self.assertIn(
            'CRITIC_VERDICT="pass"\n[[ -f "$ARTIFACTS/qa-loop.plan.final.json" ]] && reconcile_final_qa_plan_with_terminal_state || true\nwrite_verdict pass_loop_verified',
            wrapper_text,
        )
        self.assertNotIn("\\`readable/commands.md", wrapper_text)
        self.assertIn("Commands: readable/commands.md", wrapper_text)
        self.assertNotIn('set -e\n  printf \'%s\\n\' "$rc"', live_text)

    def test_fresh_smoke_release_safety_scan_detects_domain_residue_tokens(self) -> None:
        scan_python = self._extract_release_safety_scan_python()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan_root = root / "scan"
            output = root / "release-safety-scan.json"
            scan_root.mkdir()
            (scan_root / "leak.txt").write_text(
                "A public bundle must not retain cci or nonce domain residue.\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["python3", "-", str(scan_root), str(output)],
                input=scan_python,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            codes = {finding["code"] for finding in payload["findings"]}
            self.assertIn("domain_specific_token", codes)
            self.assertIn("domain_nonce_token", codes)

    def test_fresh_smoke_release_safety_scan_does_not_flag_residue_substrings(self) -> None:
        scan_python = self._extract_release_safety_scan_python()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan_root = root / "scan"
            output = root / "release-safety-scan.json"
            scan_root.mkdir()
            (scan_root / "clean.txt").write_text(
                "The words accident and announcement contain suspicious substrings but no standalone residue tokens.\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["python3", "-", str(scan_root), str(output)],
                input=scan_python,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["finding_count"], 0)

    def test_fresh_smoke_meta_scan_detects_prompt_instruction_markers(self) -> None:
        scan_python = self._extract_scan_meta_leakage_python()
        with tempfile.TemporaryDirectory() as tmp:
            artifacts = Path(tmp)
            (artifacts / "paper.full.tex").write_text(
                "\\section{Method}\n"
                "This paragraph leaks prompt meta, an internal prompt, and a figure prompt.\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                ["python3", "-", str(artifacts)],
                input=scan_python,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
            payload = json.loads((artifacts / "meta-leakage-scan.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(payload["finding_count"], 3)
            excerpts = "\n".join(finding["excerpt"] for finding in payload["findings"])
            self.assertIn("prompt meta", excerpts)
            self.assertIn("internal prompt", excerpts)
            self.assertIn("figure prompt", excerpts)

    def test_live_verification_summary_treats_metadata_seed_as_mixed_not_live(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        function_start = wrapper.index("write_live_verification_summary() {")
        function_end = wrapper.index("\n}\n\nwrite_operator_feedback", function_start) + 3
        function_text = wrapper[function_start:function_end]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workdir = root / "work"
            artifacts = root / "evidence" / "artifacts"
            run_artifacts = workdir / ".paper-orchestra" / "runs" / "po-test" / "artifacts"
            run_artifacts.mkdir(parents=True)
            artifacts.mkdir(parents=True)
            (workdir / ".paper-orchestra" / "current_session.txt").write_text("po-test", encoding="utf-8")
            (run_artifacts / "citation_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "key": "SeedOnly2026",
                            "paper_id": "S2-SEED",
                            "origin": "metadata_seed_for_live_verification",
                        },
                        {
                            "key": "Matched2026",
                            "paper_id": "S2-LIVE",
                            "origin": "metadata_seed_for_live_verification+macro_candidates",
                        },
                    ]
                ),
                encoding="utf-8",
            )
            env = dict(os.environ)
            env.update({"WORKDIR": str(workdir), "ARTIFACTS": str(artifacts), "REPO_ROOT": str(Path.cwd())})
            subprocess.run(["bash", "-c", function_text + "\nwrite_live_verification_summary"], env=env, check=True)

            payload = json.loads((artifacts / "live-verification-provenance.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["registry_count"], 2)
        self.assertEqual(payload["live_verified_count"], 1)
        self.assertEqual(payload["seed_only_count"], 1)
        self.assertTrue(payload["mixed"])
        self.assertEqual(payload["provenance_level"], "mixed")

    def test_fresh_full_live_smoke_help_is_side_effect_free(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/fresh-full-live-smoke-loop.sh", "--help"],
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertIn("Usage: scripts/fresh-full-live-smoke-loop.sh", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("command not found", result.stdout + result.stderr)
        self.assertNotIn("make_manifest", result.stdout + result.stderr)

    def test_fresh_smoke_run_step_preserves_disabled_errexit_for_semantic_exit_codes(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        start = text.index("run_step() {")
        end = text.index("\n}\n\nrun_without_papero_env", start) + 3
        run_step_definition = text[start:end]
        self.assertIn("caller_errexit", run_step_definition)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            harness = tmp_path / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"LOGS={str(tmp_path / 'logs')!r}",
                        f"READABLE={str(tmp_path / 'readable')!r}",
                        "mkdir -p \"$LOGS\" \"$READABLE\"",
                        "COMMAND_ROWS=()",
                        "redact() { cat; }",
                        "record_command_markdown() { :; }",
                        "write_timeline() { :; }",
                        run_step_definition,
                        "set +e",
                        "run_step semantic_exit bash -c 'exit 20'",
                        "rc=$?",
                        "echo survived:$rc",
                        "set -e",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=True)

        self.assertIn("survived:20", result.stdout)

    def test_docs_safe_first_run_initializes_before_run(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        environment = Path("ENVIRONMENT.md").read_text(encoding="utf-8")

        self.assertIn("./scripts/demo-mock.sh", readme)
        self.assertIn("no reference PDF required", readme)
        for text in (readme, environment):
            init_index = text.index("paperorchestra init")
            run_index = text.index("paperorchestra run", init_index)
            self.assertLess(init_index, run_index)
        self.assertNotIn("# Safe demo: no live search/model calls.\nPAPERO_REFERENCE_PDF", readme)

    def test_docs_state_run_is_not_full_quality_gate(self) -> None:
        combined = Path("README.md").read_text(encoding="utf-8") + "\n" + Path("ENVIRONMENT.md").read_text(encoding="utf-8")
        self.assertIn("run` alone", combined)
        self.assertIn("full quality", combined)

    def test_fresh_smoke_meta_leakage_scanner_covers_source_artifact_family(self) -> None:
        scanner_python = self._extract_scan_meta_leakage_python()
        samples = [
            "Table reports numbers from the supplied log.",
            "Table reports numbers from the provided log.",
            "Table reports numbers from the available log.",
            "The appendix follows the supplied file.",
            "The appendix follows the provided analysis.",
            "The appendix follows the provided analyses.",
            "The appendix follows the available file.",
            "The theorem uses the supplied evidence.",
            "The proof follows the supplied theorem statement.",
            "Following the packet, the evaluation uses these baselines.",
            "The construction follows the method packet.",
            "The discussion follows the manuscript plan.",
        ]

        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            (artifact_root / "paper.full.tex").write_text("\n".join(samples), encoding="utf-8")
            result = subprocess.run(
                ["python3", "-", str(artifact_root)],
                input=scanner_python,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            scan = (artifact_root / "meta-leakage-scan.json").read_text(encoding="utf-8")
            for phrase in [
                "supplied log",
                "provided log",
                "available log",
                "supplied file",
                "provided analysis",
                "provided analyses",
                "available file",
                "supplied evidence",
                "supplied theorem statement",
                "Following the packet",
                "method packet",
                "manuscript plan",
            ]:
                self.assertIn(phrase, scan)

    def test_fresh_smoke_meta_leakage_scanner_preserves_benign_available_analysis(self) -> None:
        scanner_python = self._extract_scan_meta_leakage_python()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            (artifact_root / "paper.full.tex").write_text(
                "Available analysis in the literature supports this baseline.",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", "-", str(artifact_root)],
                input=scanner_python,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            scan = (artifact_root / "meta-leakage-scan.json").read_text(encoding="utf-8")
            self.assertIn('"finding_count": 0', scan)

    def test_fresh_smoke_meta_leakage_scanner_preserves_scholarly_prompting_term(self) -> None:
        scanner_python = self._extract_scan_meta_leakage_python()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            (artifact_root / "paper.full.tex").write_text(
                "Iterative refinement and tool-using prompting paradigms are relevant related work.",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", "-", str(artifact_root)],
                input=scanner_python,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            scan = (artifact_root / "meta-leakage-scan.json").read_text(encoding="utf-8")
            self.assertIn('"finding_count": 0', scan)

    def test_fresh_smoke_meta_leakage_scanner_preserves_authorial_must_preserve(self) -> None:
        scanner_python = self._extract_scan_meta_leakage_python()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            (artifact_root / "paper.full.tex").write_text(
                "Authoring pipelines must preserve auditable transitions between stages.",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", "-", str(artifact_root)],
                input=scanner_python,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            scan = (artifact_root / "meta-leakage-scan.json").read_text(encoding="utf-8")
            self.assertIn('"finding_count": 0', scan)


if __name__ == "__main__":
    unittest.main()
