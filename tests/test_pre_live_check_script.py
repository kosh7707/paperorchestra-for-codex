from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unittest
from pathlib import Path


class PreLiveCheckScriptTests(unittest.TestCase):
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
        self.assertIn("PAPERO_PRE_LIVE_DIFF_CHECK_IGNORE_MATERIAL_ROOT", text)
        self.assertIn(":(exclude,glob)examples/fresh-smoke-materials/**", text)
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
        self.assertIn("PAPERO_DEMO_VERBOSE", text)
        self.assertIn("demo-mock.log", text)
        self.assertIn("--verbose", text)
        self.assertNotIn("command -v paperorchestra", text)
        self.assertNotIn("rm -rf .paper-orchestra", text)

    def test_fresh_full_live_smoke_refreshes_citation_and_omx_evidence_before_quality_gates(self) -> None:
        text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        subprocess.run(["bash", "-n", "scripts/fresh-full-live-smoke-loop.sh"], check=True)

        self.assertIn("refresh_citation_integrity_artifacts() {", text)
        for command in [
            "audit-rendered-references --quality-mode claim_safe",
            "audit-citation-integrity --quality-mode claim_safe",
            "audit-citation-integrity-critic --quality-mode claim_safe",
            "omx-review-handoff",
            "export-omx-evidence --output \"$EVIDENCE_ROOT/omx-evidence\"",
            "ralph-start --quality-mode claim_safe --max-iterations \"$MAX_ITER\" --require-live-verification --evidence-root \"$EVIDENCE_ROOT\" --dry-run",
        ]:
            self.assertIn(command, text)
        for artifact in [
            "rendered_reference_audit.json",
            "citation_intent_plan.json",
            "citation_source_match.json",
            "citation_integrity.audit.json",
            "citation_integrity.critic.json",
            "omx-review-handoff.json",
            "omx-evidence-summary.json",
            "ralph-handoff.json",
        ]:
            self.assertIn(artifact, text)
        helper_start = text.index("refresh_citation_integrity_artifacts() {")
        helper_end = text.index("preserve_operator_feedback_execution_cycle() {")
        helper = text[helper_start:helper_end]
        self.assertLess(helper.index("audit_rendered_references_${label}"), helper.index("audit_citation_integrity_${label}"))
        self.assertLess(helper.index("audit_citation_integrity_${label}"), helper.index("audit_citation_integrity_critic_${label}"))
        self.assertLess(helper.index("audit_citation_integrity_critic_${label}"), helper.index("omx_review_handoff_${label}"))
        self.assertLess(helper.index("omx_review_handoff_${label}"), helper.index("export_omx_evidence_${label}"))
        self.assertLess(helper.index("export_omx_evidence_${label}"), helper.index("ralph_start_dry_run_${label}"))
        self.assertLess(helper.index("ralph_start_dry_run_${label}"), helper.index("copy_session_artifacts"))
        ralph_line = next(line for line in helper.splitlines() if "ralph_start_dry_run_${label}" in line)
        self.assertNotIn("|| true", ralph_line)
        self.assertLess(text.index("refresh_citation_integrity_artifacts initial"), text.index("quality_eval_iter_${iter}"))
        self.assertLess(text.index("qa_loop_step_iter_${iter}"), text.index("refresh_citation_integrity_artifacts \"post_iter_${iter}\""))
        self.assertLess(text.index("review_citations_web_final_session"), text.index("refresh_citation_integrity_artifacts final"))

    def test_fresh_full_live_smoke_uses_non_tmp_codex_home_parent(self) -> None:
        text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")

        self.assertNotIn("mktemp -d /tmp/paperorchestra-smoke-codex-home.XXXXXX", text)
        self.assertIn('PAPERO_SMOKE_CODEX_HOME_PARENT', text)
        self.assertIn('$HOME/.cache/paperorchestra/smoke-codex-home', text)
        self.assertIn('mkdir -p "$SMOKE_CODEX_HOME_PARENT"', text)
        self.assertIn('SMOKE_CODEX_HOME="$(mktemp -d "$SMOKE_CODEX_HOME_PARENT/codex-home.XXXXXX")"', text)
        self.assertIn('rm -rf "$SMOKE_CODEX_HOME"', text)
        self.assertIn('rm -f "$SMOKE_CODEX_HOME/hooks.json"', text)
        self.assertIn('CODEX_HOME="$SMOKE_CODEX_HOME" "${codex_prefix[@]}" exec', text)

    def test_fresh_full_live_smoke_exports_writable_codex_home_for_omx_bridge_children(self) -> None:
        text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")

        source_index = text.index('SOURCE_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"')
        prepare_index = text.index("\nprepare_smoke_codex_home\n")
        smoke_export_index = text.index('export PAPERO_SMOKE_CODEX_HOME="$SMOKE_CODEX_HOME"')
        codex_export_index = text.index('export CODEX_HOME="$SMOKE_CODEX_HOME"')

        self.assertLess(source_index, smoke_export_index)
        self.assertLess(prepare_index, smoke_export_index)
        self.assertLess(smoke_export_index, codex_export_index)

    def test_fresh_full_live_smoke_checks_rendered_references_before_web_citation_review(self) -> None:
        text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        subprocess.run(["bash", "-n", "scripts/fresh-full-live-smoke-loop.sh"], check=True)

        self.assertIn("require_report_status_pass() {", text)
        self.assertIn("audit_rendered_references_pre_citation", text)
        self.assertIn("rendered_reference_audit.pre_citation.json", text)
        self.assertIn('QUALITY_GATE_STATUS="fail_rendered_references"', text)
        self.assertIn('MANUSCRIPT_READINESS="blocked_rendered_references"', text)
        self.assertLess(
            text.index("run_step audit_rendered_references_pre_citation"),
            text.index("run_retryable_step review_citations_web_initial"),
        )
        self.assertLess(
            text.index("rendered_reference_pre_citation_gate"),
            text.index("run_retryable_step review_citations_web_initial"),
        )
        self.assertLess(text.index("refresh_citation_integrity_artifacts final"), text.index("quality_eval_final"))
        self.assertIn("write-intro-related", text)
        self.assertIn("--allow-recoverable-contract-issues", text)

    def test_fresh_full_live_smoke_report_status_gate_fails_non_pass_reports(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        start = wrapper.index("require_report_status_pass() {")
        end = wrapper.index("\n}\n\nsmoke_retry_sleep", start) + 3
        function_text = wrapper[start:end]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            passing = root / "passing.json"
            failing = root / "failing.json"
            passing.write_text(json.dumps({"report": {"status": "pass", "failing_codes": []}}), encoding="utf-8")
            failing.write_text(
                json.dumps(
                    {
                        "report": {
                            "status": "fail",
                            "failing_codes": ["rendered_reference_unknown_metadata"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            harness = root / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        function_text,
                        f"require_report_status_pass {str(passing)!r}",
                        f"if require_report_status_pass {str(failing)!r} >{str(root / 'fail.out')!r} 2>{str(root / 'fail.err')!r}; then exit 44; fi",
                        "exit 0",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn(
                "rendered_reference_unknown_metadata",
                (root / "fail.err").read_text(encoding="utf-8"),
            )

    def test_fresh_full_live_smoke_skips_empty_reference_metadata_seed(self) -> None:
        text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        subprocess.run(["bash", "-n", "scripts/fresh-full-live-smoke-loop.sh"], check=True)

        self.assertIn("grep -Eq '^[[:space:]]*@' inputs/reference_metadata_seed.bib", text)
        self.assertIn("skip import_reference_metadata_seed: no explicit bibliographic seed entries were generated", text)
        self.assertIn('COMMAND_ROWS+=("import_reference_metadata_seed|0")', text)
        self.assertIn("research-prior-work --source \"fresh material smoke\" --import --require-complete-metadata", text)
        self.assertLess(
            text.index("grep -Eq '^[[:space:]]*@' inputs/reference_metadata_seed.bib"),
            text.index("run_retryable_step research_prior_work"),
        )

    def test_pre_live_secret_scan_does_not_scan_generated_review_logs(self) -> None:
        text = Path("scripts/pre-live-check.sh").read_text(encoding="utf-8")
        line = next(line for line in text.splitlines() if line.startswith("run_step secret_scan "))
        self.assertNotIn(" review ", f" {line} ")
        self.assertIn("README.md ENVIRONMENT.md NOTICE.md docs paperorchestra tests scripts examples pyproject.toml", line)

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
        self.assertIn("--probe-evidence-bundle", Path("paperorchestra/mcp_smoke.py").read_text(encoding="utf-8"))
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
            for transport in ("content-length", "newline"):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(path),
                        "--config",
                        str(config),
                        "--cwd",
                        str(root),
                        "--transport",
                        transport,
                        "--json",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, f"{transport}: {result.stderr}")
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["transport"], transport)
                self.assertTrue(payload["config"]["registered"])
                self.assertTrue(payload["server"]["initialize_ok"])
                self.assertTrue(payload["server"]["tools_list_ok"])
                self.assertGreaterEqual(payload["server"]["tool_count"], 50)
                self.assertTrue(payload["server"]["expected_tools_present"])
                self.assertTrue(payload["server"]["status_call_reached_server"])
                self.assertFalse(payload["server"]["evidence_bundle_probe"]["checked"])
                self.assertFalse(payload["active_session_attachment"]["checked"])

    def test_paperorchestra_mcp_smoke_can_probe_evidence_bundle_explicitly(self) -> None:
        from paperorchestra.mcp_smoke import build_mcp_smoke_report

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
            report = build_mcp_smoke_report(
                config_path=config,
                cwd=root,
                transport="newline",
                probe_evidence_bundle=True,
            )
            probe = report["server"]["evidence_bundle_probe"]
            output_dir = Path(probe["output_dir"])
            manifest_exists = Path(probe["manifest_path"]).exists()
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.rglob("*.json"))

        self.assertEqual(report["status"], "ok")
        self.assertTrue(probe["checked"])
        self.assertTrue(probe["ok"])
        self.assertEqual(probe["execution"], "bounded_plan_only")
        self.assertTrue(manifest_exists)
        self.assertFalse(probe["paper_full_tex_present"])
        self.assertFalse(probe["bundle_contains_absolute_cwd"])
        self.assertNotIn(str(root), rendered)

    def test_mcp_smoke_read_exact_times_out_on_partial_body_stall(self) -> None:
        from paperorchestra.mcp_smoke import _read_exact

        read_fd, write_fd = os.pipe()

        def writer() -> None:
            try:
                os.write(write_fd, b"ab")
                time.sleep(1.0)
                os.write(write_fd, b"cd")
            except OSError:
                pass
            finally:
                try:
                    os.close(write_fd)
                except OSError:
                    pass

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        reader = os.fdopen(read_fd, "rb", buffering=0)
        started = time.monotonic()
        try:
            with self.assertRaises(TimeoutError):
                _read_exact(reader, 4, 0.2)
        finally:
            reader.close()
        self.assertLess(time.monotonic() - started, 0.8)

    def test_codex_mcp_attach_smoke_script_is_isolated_and_detects_tool_call(self) -> None:
        path = Path("scripts/smoke-codex-mcp-attach.sh")
        self.assertTrue(path.exists())
        self.assertTrue(path.stat().st_mode & 0o111)
        text = path.read_text(encoding="utf-8")
        self.assertIn("--ignore-user-config", text)
        self.assertIn("mcp_servers.paperorchestra.command", text)
        self.assertIn("mcp_tool_call", text)
        self.assertIn("server", text)
        self.assertIn("paperorchestra", text)
        self.assertIn("status", text)
        self.assertIn("PAPERO_ATTACH_SMOKE_TOOL", text)
        self.assertIn("inspect_state", text)
        self.assertIn("tool_name", text)
        self.assertIn("config_mutation", text)

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
        self.assertIn('PAPERO_CODEX_CLI_PREFIX', wrapper_text)
        self.assertIn('codex_cli_prefix_words()', wrapper_text)
        self.assertIn('CODEX_HOME="$SMOKE_CODEX_HOME" "${codex_prefix[@]}" exec', wrapper_text)
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
        self.assertIn('--expected-material-root "$EXPECTED_MATERIAL_ROOT"', wrapper_text)
        self.assertIn("run_step unittest bash -c 'run_without_papero_env", wrapper_text)
        self.assertIn("run_step pre_live_all bash -c 'run_without_papero_env", wrapper_text)
        self.assertIn("env PAPERO_PRE_LIVE_DIFF_CHECK_IGNORE_MATERIAL_ROOT=1 bash scripts/pre-live-check.sh --all", wrapper_text)
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
        scanner = Path("scripts/release-safety-scan.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scan_root = root / "scan"
            output = root / "release-safety-scan.json"
            scan_root.mkdir()
            (scan_root / "leak.txt").write_text(
                (
                    "A public bundle must not retain "
                    + ("c" + "ci")
                    + " or "
                    + ("non" + "ce")
                    + " domain residue.\n"
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, str(scanner), str(scan_root), str(output)],
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
        scanner = Path("scripts/release-safety-scan.py")
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
                [sys.executable, str(scanner), str(scan_root), str(output)],
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
        self.assertIn("--expected-material-root", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("command not found", result.stdout + result.stderr)
        self.assertNotIn("make_manifest", result.stdout + result.stderr)

    def test_fresh_full_live_smoke_dry_run_contract_redacts_custom_codex_cli_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            raw_prefix = "custom-codex --auth-profile private"
            env["PAPERO_CODEX_CLI_PREFIX"] = raw_prefix
            result = subprocess.run(
                [
                    "bash",
                    "scripts/fresh-full-live-smoke-loop.sh",
                    "--dry-run-contract",
                    "--evidence-root",
                    str(Path(tmp) / "evidence"),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )

        payload = json.loads(result.stdout)
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn(raw_prefix, rendered)
        self.assertNotIn("custom-codex", rendered)
        self.assertNotIn("--auth-profile", rendered)
        self.assertIn("codex_cli_prefix_label", payload)
        self.assertIn("critic_exec_argv_prefix_label", payload)
        contract = payload["provider_wrapper_contract"]
        self.assertIn("codex_cli_prefix_label", contract)
        self.assertIn("codex_cli_prefix_sha256", contract)
        self.assertNotIn("codex_cli_prefix", contract)
        self.assertNotIn("exec_argv_prefix", contract["modes"]["gen"])
        self.assertNotIn("exec_argv_prefix", contract["modes"]["web"])
        self.assertIn("exec_argv_prefix_label", contract["modes"]["web"])
        self.assertEqual(contract["modes"]["gen"]["web_search_capable"], False)
        self.assertEqual(contract["modes"]["web"]["web_search_capable"], True)

    def test_fresh_smoke_public_evidence_metadata_is_release_safety_clean_under_private_marker_paths(self) -> None:
        wrapper_text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")
        run_step_start = wrapper_text.index("redact() {")
        run_step_end = wrapper_text.index("\n}\n\nrun_without_papero_env", run_step_start) + 3
        run_step_helpers = wrapper_text[run_step_start:run_step_end]
        scanner = Path("scripts/release-safety-scan.py")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "paperorchestra-private-evidence"
            material = root / "paperorchestra-private-material"
            env = os.environ.copy()
            raw_prefix = "custom-codex --auth-profile private"
            env["PAPERO_CODEX_CLI_PREFIX"] = raw_prefix
            result = subprocess.run(
                [
                    "bash",
                    "scripts/fresh-full-live-smoke-loop.sh",
                    "--dry-run-contract",
                    "--evidence-root",
                    str(evidence),
                    "--material-root",
                    str(material),
                    "--expected-material-root",
                    str(material),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )
            (evidence / "dry-run-contract.json").write_text(result.stdout, encoding="utf-8")

            harness = root / "run-step-harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"REPO_ROOT={str(Path.cwd())!r}",
                        f"EVIDENCE_ROOT={str(evidence)!r}",
                        'LOGS="$EVIDENCE_ROOT/logs"',
                        'READABLE="$EVIDENCE_ROOT/readable"',
                        "COMMAND_ROWS=()",
                        'mkdir -p "$LOGS" "$READABLE"',
                        run_step_helpers,
                        f"run_step synthetic_private_path_command printf '%s\\n' {str(material)!r}",
                        f"run_step synthetic_wrapped_provider_command printf '%s\\n' --provider shell --provider-command '[\"bash\",\"{str(evidence / 'provider-wrap.sh')}\",\"gen\"]'",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(["bash", str(harness)], check=True)

            output = root / "release-safety-scan.json"
            scan = subprocess.run(
                [sys.executable, str(scanner), str(evidence), str(output)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(scan.returncode, 0, scan.stderr + scan.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["blocking_finding_count"], 0)
            self.assertEqual(payload["finding_count"], 0)
            rendered = "\n".join(
                [
                    (evidence / "README.md").read_text(encoding="utf-8"),
                    (evidence / "provider-wrap.contract.json").read_text(encoding="utf-8"),
                    (evidence / "dry-run-contract.json").read_text(encoding="utf-8"),
                    (evidence / "logs" / "synthetic_private_path_command.command").read_text(encoding="utf-8"),
                    (evidence / "logs" / "synthetic_wrapped_provider_command.command").read_text(encoding="utf-8"),
                ]
            )
            self.assertNotIn(str(evidence), rendered)
            self.assertNotIn(str(material), rendered)
            self.assertNotIn("paperorchestra-private", rendered)
            self.assertNotIn(raw_prefix, rendered)
            self.assertNotIn("custom-codex", rendered)
            self.assertIn("provider-wrap.sh", (evidence / "logs" / "synthetic_wrapped_provider_command.command").read_text(encoding="utf-8"))

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

    def test_fresh_smoke_codex_last_message_retries_model_capacity_once(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        prefix_start = text.index("codex_cli_prefix_words() {")
        prefix_end = text.index("\n}\n\nrun_release_safety_scan", prefix_start) + 3
        retry_start = text.index("retryable_transport_file() {")
        retry_end = text.index("\n}\n\nwrite_operator_feedback_author_failure", retry_start) + 3
        function_text = text[prefix_start:prefix_end] + "\n\n" + text[retry_start:retry_end]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "fake-codex"
            counter = root / "attempt-count.txt"
            fake.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "count=0\n"
                f"counter={str(counter)!r}\n"
                "[[ -f \"$counter\" ]] && count=$(cat \"$counter\")\n"
                "count=$((count + 1))\n"
                "printf '%s\\n' \"$count\" > \"$counter\"\n"
                "out=''\n"
                "want_out=0\n"
                "for arg in \"$@\"; do\n"
                "  if [[ \"$want_out\" == 1 ]]; then out=\"$arg\"; want_out=0; continue; fi\n"
                "  [[ \"$arg\" == '--output-last-message' ]] && want_out=1\n"
                "done\n"
                "if [[ \"$count\" == 1 ]]; then\n"
                "  echo 'ERROR: Selected model is at capacity. Please try a different model.' >&2\n"
                "  exit 1\n"
                "fi\n"
                "printf 'final response\\n' > \"$out\"\n"
                "echo 'ok stdout'\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            prompt = root / "prompt.md"
            prompt.write_text("hello\n", encoding="utf-8")
            harness = root / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"PYTHONPATH={str(Path.cwd())!r}",
                        "export PYTHONPATH",
                        f"REPO_ROOT={str(Path.cwd())!r}",
                        f"SMOKE_CODEX_HOME={str(root / 'codex-home')!r}",
                        f"PAPERO_CODEX_CLI_PREFIX={str(fake)!r}",
                        "PAPERO_CODEX_RETRY_ATTEMPTS=1",
                        "PAPERO_CODEX_RETRY_BACKOFF_SECONDS=0",
                        "export REPO_ROOT SMOKE_CODEX_HOME PAPERO_CODEX_CLI_PREFIX PAPERO_CODEX_RETRY_ATTEMPTS PAPERO_CODEX_RETRY_BACKOFF_SECONDS",
                        "mkdir -p \"$SMOKE_CODEX_HOME\"",
                        "redact() { cat; }",
                        "write_timeline() { :; }",
                        function_text,
                        f"run_codex_last_message capacity {str(prompt)!r} {str(root / 'response.md')!r} {str(root / 'stdout.log')!r} {str(root / 'stderr.log')!r} {str(root / 'exitcode')!r} gpt-5.5 high",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(counter.read_text(encoding="utf-8").strip(), "2")
            self.assertEqual((root / "response.md").read_text(encoding="utf-8"), "final response\n")
            ledger = [
                json.loads(line)
                for line in (root / "exitcode.retry.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([entry["exit_code"] for entry in ledger], [1, 0])
            self.assertTrue(ledger[0]["retryable_transport"])
            self.assertTrue(ledger[1]["replayed"])

    def test_fresh_smoke_step_retry_uses_matching_provider_trace(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        retry_start = text.index("retryable_transport_file() {")
        retry_end = text.index("\n}\n\nwrite_operator_feedback_author_failure", retry_start) + 3
        function_text = text[retry_start:retry_end]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"PYTHONPATH={str(Path.cwd())!r}",
                        f"REPO_ROOT={str(Path.cwd())!r}",
                        f"EVIDENCE_ROOT={str(root)!r}",
                        f"LOGS={str(root / 'logs')!r}",
                        "export PYTHONPATH REPO_ROOT EVIDENCE_ROOT LOGS",
                        "mkdir -p \"$LOGS\" \"$EVIDENCE_ROOT/provider-traces\"",
                        "PAPERO_SMOKE_STEP_RETRY_ATTEMPTS=1",
                        "PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS=0",
                        "PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS=0",
                        "export PAPERO_SMOKE_STEP_RETRY_ATTEMPTS PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS",
                        "write_timeline() { :; }",
                        "run_step() {",
                        "  local label=\"$1\"; shift",
                        f"  local counter={str(root / 'count.txt')!r}",
                        "  local count=0",
                        "  [[ -f \"$counter\" ]] && count=$(cat \"$counter\")",
                        "  count=$((count + 1))",
                        "  printf '%s\\n' \"$count\" > \"$counter\"",
                        "  if [[ \"$count\" == 1 ]]; then",
                        "    : > \"$LOGS/${label}.stderr.log\"",
                        "    cat > \"$EVIDENCE_ROOT/provider-traces/0001-gen.meta.json\" <<JSON",
                        "{\"schema_version\":\"provider-trace-meta/1\",\"command_name\":\"$label\",\"stderr\":\"0001-gen.stderr.log\",\"retry_ledger\":\"0001-gen.retry.jsonl\"}",
                        "JSON",
                        "    echo 'ERROR: selected model is at capacity' > \"$EVIDENCE_ROOT/provider-traces/0001-gen.stderr.log\"",
                        "    echo '{\"retryable_transport\": true}' > \"$EVIDENCE_ROOT/provider-traces/0001-gen.retry.jsonl\"",
                        "    return 1",
                        "  fi",
                        "  : > \"$LOGS/${label}.stderr.log\"",
                        "  return 0",
                        "}",
                        function_text,
                        "run_retryable_step outline bash -c 'true'",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual((root / "count.txt").read_text(encoding="utf-8").strip(), "2")
            ledger = [
                json.loads(line)
                for line in (root / "logs" / "outline.step-retry.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([row["exit_code"] for row in ledger], [1, 0])
            self.assertTrue(ledger[0]["retryable_transport"])
            self.assertTrue(ledger[1]["replayed"])

    def test_fresh_smoke_step_retry_classifies_usage_limit_provider_stderr(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        retry_start = text.index("retryable_transport_file() {")
        retry_end = text.index("\n}\n\nwrite_operator_feedback_author_failure", retry_start) + 3
        function_text = text[retry_start:retry_end]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"PYTHONPATH={str(Path.cwd())!r}",
                        f"REPO_ROOT={str(Path.cwd())!r}",
                        f"EVIDENCE_ROOT={str(root)!r}",
                        f"LOGS={str(root / 'logs')!r}",
                        "export PYTHONPATH REPO_ROOT EVIDENCE_ROOT LOGS",
                        "mkdir -p \"$LOGS\" \"$EVIDENCE_ROOT/provider-traces\"",
                        "PAPERO_SMOKE_STEP_RETRY_ATTEMPTS=1",
                        "PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS=0",
                        "PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS=0",
                        "export PAPERO_SMOKE_STEP_RETRY_ATTEMPTS PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS",
                        "write_timeline() { :; }",
                        "run_step() {",
                        "  local label=\"$1\"; shift",
                        f"  local counter={str(root / 'count.txt')!r}",
                        "  local count=0",
                        "  [[ -f \"$counter\" ]] && count=$(cat \"$counter\")",
                        "  count=$((count + 1))",
                        "  printf '%s\\n' \"$count\" > \"$counter\"",
                        "  if [[ \"$count\" == 1 ]]; then",
                        "    : > \"$LOGS/${label}.stderr.log\"",
                        "    cat > \"$EVIDENCE_ROOT/provider-traces/0001-web.meta.json\" <<JSON",
                        "{\"schema_version\":\"provider-trace-meta/1\",\"command_name\":\"$label\",\"stderr\":\"0001-web.stderr.log\",\"exitcode\":\"0001-web.exitcode\",\"retry_ledger\":\"0001-web.retry.jsonl\"}",
                        "JSON",
                        "    echo 1 > \"$EVIDENCE_ROOT/provider-traces/0001-web.exitcode\"",
                        "    echo \"ERROR: You've hit your usage limit. Visit settings or try again at 10:17 AM.\" > \"$EVIDENCE_ROOT/provider-traces/0001-web.stderr.log\"",
                        "    echo '{\"retryable_transport\": false, \"exit_code\": 1}' > \"$EVIDENCE_ROOT/provider-traces/0001-web.retry.jsonl\"",
                        "    return 1",
                        "  fi",
                        "  : > \"$LOGS/${label}.stderr.log\"",
                        "  return 0",
                        "}",
                        function_text,
                        "run_retryable_step review_citations_web_initial bash -c 'true'",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual((root / "count.txt").read_text(encoding="utf-8").strip(), "2")
            ledger = [
                json.loads(line)
                for line in (root / "logs" / "review_citations_web_initial.step-retry.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            self.assertEqual([row["exit_code"] for row in ledger], [1, 0])
            self.assertTrue(ledger[0]["retryable_transport"])
            self.assertTrue(ledger[1]["replayed"])

    def test_fresh_smoke_step_retry_does_not_replay_non_retryable_failure(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        retry_start = text.index("retryable_transport_file() {")
        retry_end = text.index("\n}\n\nwrite_operator_feedback_author_failure", retry_start) + 3
        function_text = text[retry_start:retry_end]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"PYTHONPATH={str(Path.cwd())!r}",
                        f"REPO_ROOT={str(Path.cwd())!r}",
                        f"EVIDENCE_ROOT={str(root)!r}",
                        f"LOGS={str(root / 'logs')!r}",
                        "export PYTHONPATH REPO_ROOT EVIDENCE_ROOT LOGS",
                        "mkdir -p \"$LOGS\" \"$EVIDENCE_ROOT/provider-traces\"",
                        "PAPERO_SMOKE_STEP_RETRY_ATTEMPTS=1",
                        "PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS=0",
                        "PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS=0",
                        "export PAPERO_SMOKE_STEP_RETRY_ATTEMPTS PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS",
                        "write_timeline() { :; }",
                        "run_step() {",
                        "  local label=\"$1\"; shift",
                        f"  local counter={str(root / 'count.txt')!r}",
                        "  local count=0",
                        "  [[ -f \"$counter\" ]] && count=$(cat \"$counter\")",
                        "  count=$((count + 1))",
                        "  printf '%s\\n' \"$count\" > \"$counter\"",
                        "  echo 'semantic validation failure' > \"$LOGS/${label}.stderr.log\"",
                        "  return 1",
                        "}",
                        function_text,
                        "set +e",
                        "run_retryable_step outline bash -c 'true'",
                        "rc=$?",
                        "set -e",
                        "echo rc:$rc",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("rc:1", result.stdout)
            self.assertEqual((root / "count.txt").read_text(encoding="utf-8").strip(), "1")
            ledger = [
                json.loads(line)
                for line in (root / "logs" / "outline.step-retry.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(ledger), 1)
            self.assertFalse(ledger[0]["retryable_transport"])

    def test_fresh_smoke_step_retry_ignores_successful_provider_internal_retry(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        retry_start = text.index("retryable_transport_file() {")
        retry_end = text.index("\n}\n\nwrite_operator_feedback_author_failure", retry_start) + 3
        function_text = text[retry_start:retry_end]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        f"PYTHONPATH={str(Path.cwd())!r}",
                        f"REPO_ROOT={str(Path.cwd())!r}",
                        f"EVIDENCE_ROOT={str(root)!r}",
                        f"LOGS={str(root / 'logs')!r}",
                        "export PYTHONPATH REPO_ROOT EVIDENCE_ROOT LOGS",
                        "mkdir -p \"$LOGS\" \"$EVIDENCE_ROOT/provider-traces\"",
                        "PAPERO_SMOKE_STEP_RETRY_ATTEMPTS=1",
                        "PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS=0",
                        "PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS=0",
                        "export PAPERO_SMOKE_STEP_RETRY_ATTEMPTS PAPERO_SMOKE_STEP_RETRY_BACKOFF_SECONDS PAPERO_SMOKE_STEP_RETRY_JITTER_SECONDS",
                        "write_timeline() { :; }",
                        "run_step() {",
                        "  local label=\"$1\"; shift",
                        f"  local counter={str(root / 'count.txt')!r}",
                        "  local count=0",
                        "  [[ -f \"$counter\" ]] && count=$(cat \"$counter\")",
                        "  count=$((count + 1))",
                        "  printf '%s\\n' \"$count\" > \"$counter\"",
                        "  echo 'semantic validation failure after provider returned' > \"$LOGS/${label}.stderr.log\"",
                        "  cat > \"$EVIDENCE_ROOT/provider-traces/0001-gen.meta.json\" <<JSON",
                        "{\"schema_version\":\"provider-trace-meta/1\",\"command_name\":\"$label\",\"stderr\":\"0001-gen.stderr.log\",\"exitcode\":\"0001-gen.exitcode\",\"retry_ledger\":\"0001-gen.retry.jsonl\"}",
                        "JSON",
                        "  echo 'ERROR: selected model is at capacity' > \"$EVIDENCE_ROOT/provider-traces/0001-gen.stderr.log\"",
                        "  echo '0' > \"$EVIDENCE_ROOT/provider-traces/0001-gen.exitcode\"",
                        "  echo '{\"retryable_transport\": true, \"exit_code\": 1}' > \"$EVIDENCE_ROOT/provider-traces/0001-gen.retry.jsonl\"",
                        "  echo '{\"retryable_transport\": false, \"exit_code\": 0}' >> \"$EVIDENCE_ROOT/provider-traces/0001-gen.retry.jsonl\"",
                        "  return 1",
                        "}",
                        function_text,
                        "set +e",
                        "run_retryable_step outline bash -c 'true'",
                        "rc=$?",
                        "set -e",
                        "echo rc:$rc",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(["bash", str(harness)], text=True, capture_output=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("rc:1", result.stdout)
            self.assertEqual((root / "count.txt").read_text(encoding="utf-8").strip(), "1")
            ledger = [
                json.loads(line)
                for line in (root / "logs" / "outline.step-retry.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(ledger), 1)
            self.assertFalse(ledger[0]["retryable_transport"])

    def test_fresh_smoke_step_retry_only_wraps_provider_backed_stages(self) -> None:
        wrapper_text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")

        for name in [
            "research_prior_work",
            "outline",
            "generate_plots",
            "write_intro_related",
            "write_sections",
            "review",
            "review_citations_web_initial",
        ]:
            self.assertIn(f"run_retryable_step {name}", wrapper_text)

        for name in [
            "plan_narrative",
            "compile_initial",
            "material_invariance",
            "validate_current",
            "quality_eval_iter_",
            "qa_loop_plan_iter_",
            "build_source_obligations",
        ]:
            self.assertNotIn(f"run_retryable_step {name}", wrapper_text)

    def test_fresh_smoke_operator_feedback_author_failure_is_diagnosable(self) -> None:
        wrapper_text = Path("scripts/fresh-full-live-smoke-loop.sh").read_text(encoding="utf-8")

        for token in [
            "write_operator_feedback_author_failure()",
            "operator-feedback-author-failure/1",
            "operator_feedback_author_retryable_transport_exhausted",
            "retryable_transport_detected",
            "operator-feedback-author.cycle-${cycle}.failure.json",
            "operator_feedback_author",
            "expected_feedback_json",
        ]:
            self.assertIn(token, wrapper_text)
        self.assertIn(
            'write_operator_feedback_author_failure "$cycle" "$rc"',
            wrapper_text,
        )
        self.assertIn(
            'operator_failure_artifact="operator-feedback/operator-feedback-author.cycle-${OPERATOR_FEEDBACK_CYCLES}.failure.json"',
            wrapper_text,
        )
        self.assertIn(
            'fail_now fail_loop_feedback_not_reflected "$operator_failure_predicate" "\\"${operator_failure_artifact}\\"" 1',
            wrapper_text,
        )

    def test_run_without_papero_env_preserves_intentional_pre_live_diff_check_override(self) -> None:
        wrapper = Path("scripts/fresh-full-live-smoke-loop.sh")
        text = wrapper.read_text(encoding="utf-8")
        start = text.index("run_without_papero_env() {")
        end = text.index("\n}\nexport -f run_without_papero_env", start) + 3
        function_text = text[start:end]

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            harness = Path(tmp) / "harness.sh"
            harness.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env bash",
                        "set -euo pipefail",
                        function_text,
                        "export PAPERO_SHOULD_BE_CLEARED=1",
                        "run_without_papero_env \"$1\" env PAPERO_PRE_LIVE_DIFF_CHECK_IGNORE_MATERIAL_ROOT=1 bash -c '",
                        "  test -z \"${PAPERO_SHOULD_BE_CLEARED:-}\"",
                        "  test \"${PAPERO_PRE_LIVE_DIFF_CHECK_IGNORE_MATERIAL_ROOT:-}\" = 1",
                        "'",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(["bash", str(harness), str(repo)], check=True)

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

    def test_fresh_smoke_meta_leakage_scanner_flags_process_residue_title(self) -> None:
        scanner_python = self._extract_scan_meta_leakage_python()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            (artifact_root / "paper.full.tex").write_text(
                "\\documentclass{article}\n"
                "\\title{Artifact-Governed Drafting with Promotion-Time Validation}\n"
                "\\begin{document}\\maketitle\\section{Introduction}Clean technical text.\\end{document}\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", "-", str(artifact_root)],
                input=scanner_python,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads((artifact_root / "meta-leakage-scan.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "fail")
            self.assertGreaterEqual(payload["finding_count"], 2)
            patterns = {finding["pattern"] for finding in payload["findings"]}
            self.assertIn(r"artifact[-\s]+governed\s+drafting", patterns)
            self.assertIn(r"promotion[-\s]+time\s+validation", patterns)

    def test_fresh_smoke_meta_leakage_scanner_does_not_ban_artifact_or_validation_terms(self) -> None:
        scanner_python = self._extract_scan_meta_leakage_python()
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp)
            (artifact_root / "paper.full.tex").write_text(
                "Artifact validation is a normal phrase in reproducibility and systems papers.",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["python3", "-", str(artifact_root)],
                input=scanner_python,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads((artifact_root / "meta-leakage-scan.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["finding_count"], 0)

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

    def test_pre_live_check_unittest_selectors_are_loadable(self) -> None:
        text = Path("scripts/pre-live-check.sh").read_text(encoding="utf-8")
        selectors = sorted(set(re.findall(r"tests\.[A-Za-z0-9_\.]+\.test_[A-Za-z0-9_]+", text)))
        self.assertTrue(selectors)

        def iter_cases(suite: unittest.TestSuite):
            for item in suite:
                if isinstance(item, unittest.TestSuite):
                    yield from iter_cases(item)
                else:
                    yield item

        loader = unittest.TestLoader()
        broken = []
        for selector in selectors:
            suite = loader.loadTestsFromName(selector)
            failed = [case for case in iter_cases(suite) if case.__class__.__name__ == "_FailedTest"]
            if failed:
                broken.append(selector)
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
