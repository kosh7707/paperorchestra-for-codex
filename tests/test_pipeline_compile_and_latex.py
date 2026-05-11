from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_test_support import *


class PipelineCompileAndLatexTests(PipelineTestCase):
    """Compile environment, status/export, fidelity, and LaTeX regression tests split out of the former PipelineTests monolith."""

    def test_fidelity_audit_report_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="model",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )
            path, payload = record_fidelity_report(root)
            self.assertTrue(path.exists())
            self.assertIn("overall_status", payload)
            self.assertTrue(payload["checks"])
            codes = {check["code"] for check in payload["checks"]}
            self.assertIn("agentreview_substitute_surface", codes)
            self.assertIn("review_gate_comparison_surface", codes)
            self.assertIn("search_grounding_substitute_surface", codes)
            self.assertIn("benchmark_eval_surface", codes)
            self.assertIn("generated_citation_title_surface", codes)
            self.assertIn("citation_partition_scaffold_surface", codes)

    def test_fidelity_audit_detects_repo_pdf_and_eval_artifacts_after_scaffold_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            run_pipeline(
                root,
                provider=MockProvider(),
                discovery_mode="search-grounded",
                verify_mode="mock",
                refine_iterations=1,
                compile_paper=False,
            )

            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "seed_answers.json").write_text(
                json.dumps(
                    {
                        "baselines": ["Single Agent", "AI Scientist-v2"],
                        "datasets_or_benchmarks": ["PaperWritingBench (200 papers from CVPR 2025 and ICLR 2025)"],
                    }
                ),
                encoding="utf-8",
            )
            (reference_dir / "results.md").write_text(
                "Absolute win-rate margins of 50%–68% in literature review quality and 14%–38% in overall manuscript quality.",
                encoding="utf-8",
            )
            (reference_dir / "methodology.md").write_text("Method excerpt", encoding="utf-8")
            (reference_dir / "task_and_dataset.md").write_text("Task excerpt", encoding="utf-8")
            (reference_dir / "template.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
            source_pdf = reference_dir / "paperorchestra-reference.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\n% mock reference pdf\n")
            reference_case = write_reference_benchmark_case(
                reference_dir, reference_dir / "benchmark_case.json", source_pdf=source_pdf
            )

            old_reference_pdf = os.environ.get("PAPERO_REFERENCE_PDF")
            os.environ["PAPERO_REFERENCE_PDF"] = str(source_pdf)
            try:
                state = load_session(root)
                artifact_dir = Path(state.artifacts.paper_full_tex).resolve().parent
                write_session_eval_summary(root, artifact_dir / "session_eval_summary.json")
                write_review_gate_comparison(root, artifact_dir / "review_gate_comparison.json")
                write_generated_citation_titles(root, artifact_dir / "generated_citation_titles.json")
                write_reference_comparison(reference_case, root, artifact_dir / "reference_comparison.json")
                write_reference_case_partition_scaffold(reference_case, artifact_dir / "reference_case_partition_scaffold.json")
                write_reference_case_partitioned_citation_coverage(
                    reference_case, root, artifact_dir / "reference_case_partitioned_citation_coverage.json"
                )

                _, payload = record_fidelity_report(root)
                statuses = {check["code"]: check["status"] for check in payload["checks"]}
                self.assertEqual(statuses["paper_source_present"], "implemented")
                self.assertEqual(statuses["benchmark_eval_surface"], "implemented")
                self.assertEqual(statuses["generated_citation_title_surface"], "implemented")
                self.assertEqual(statuses["citation_partition_scaffold_surface"], "implemented")
                summary = json.loads(
                    write_session_eval_summary(root, artifact_dir / "session_eval_summary.json").read_text(encoding="utf-8")
                )
                self.assertEqual(summary["fidelity_overall_status"], "partial")
            finally:
                if old_reference_pdf is None:
                    os.environ.pop("PAPERO_REFERENCE_PDF", None)
                else:
                    os.environ["PAPERO_REFERENCE_PDF"] = old_reference_pdf

    def test_compile_environment_report_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_session_with_minimal_inputs(root)
            path, payload = record_compile_environment_report(root)
            self.assertTrue(path.exists())
            self.assertIn("ready_for_compile", payload)
            self.assertIn("install_commands", payload)
            self.assertIn("bootstrap_script_path", payload)
            self.assertIn("user_space_probe", payload)
            self.assertIn("cargo_available", payload["user_space_probe"])

    def test_check_compile_env_cli_works_without_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["check-compile-env"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(Path(payload["path"]).exists())
            self.assertIn(".paper-orchestra/preflight/compile-environment.json", payload["path"])
            self.assertIn("ready_for_compile", payload["report"])
            self.assertIn("ready_for_compile", payload)
            self.assertEqual(payload["ready_for_compile"], payload["report"]["ready_for_compile"])

    def test_status_summary_highlights_main_outputs_and_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text('{"overall_score": 0.8}\n', encoding="utf-8")
            repro = artifact_path(root, "reproducibility.audit.json")
            repro.write_text('{"verdict": "BLOCK"}\n', encoding="utf-8")
            state.current_phase = "draft_complete"
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.latest_review_json = str(review)
            state.artifacts.latest_reproducibility_json = str(repro)
            save_session(root, state)
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["status", "--summary"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn(f"Session: {state.session_id}", output)
        self.assertIn("Phase: draft_complete", output)
        self.assertIn(str(paper), output)
        self.assertIn(str(review), output)
        self.assertIn("paperorchestra check-compile-env", output)

    def test_export_artifacts_copies_current_main_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = self._init_session_with_minimal_inputs(root)
            paper = artifact_path(root, "paper.full.tex")
            paper.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
            pdf = root / ".paper-orchestra" / "runs" / state.session_id / "build" / "compiled" / "paper.full.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.5\n")
            refs = artifact_path(root, "references.bib")
            refs.write_text("@article{x,title={X}}\n", encoding="utf-8")
            review = review_path(root, "review.latest.json")
            review.write_text('{"overall_score": 0.8}\n', encoding="utf-8")
            quality_gate = artifact_path(root, "quality-gate.report.json")
            quality_gate.write_text('{"schema_version":"quality-gate/1","decision":{"verdict":"pass"}}\n', encoding="utf-8")
            state.artifacts.paper_full_tex = str(paper)
            state.artifacts.compiled_pdf = str(pdf)
            state.artifacts.references_bib = str(refs)
            state.artifacts.latest_review_json = str(review)
            save_session(root, state)
            out_dir = root / "out"
            old_cwd = Path.cwd()
            stdout = io.StringIO()
            try:
                os.chdir(root)
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["export-artifacts", "--output", str(out_dir), "--include-all-artifacts", "--json"])
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "ok")
            self.assertTrue((out_dir / "paper.full.tex").exists())
            self.assertTrue((out_dir / "paper.full.pdf").exists())
            self.assertTrue((out_dir / "references.bib").exists())
            self.assertTrue((out_dir / "review.latest.json").exists())
            self.assertTrue((out_dir / "quality-gate.report.json").exists())
            copied_labels = {item["label"] for item in payload["copied"]}
            self.assertIn("quality_gate_report", copied_labels)
            self.assertTrue((out_dir / "session.json").exists())
            self.assertTrue((out_dir / "artifacts" / "paper.full.tex").exists())

    def test_compile_env_bootstrap_uses_root_commands_without_sudo(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/apt-get" if name == "apt-get" else None

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=0), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)
            self.assertTrue(report.bootstrap_script_path)
            script = Path(report.bootstrap_script_path).read_text(encoding="utf-8")

        self.assertTrue(report.install_context["is_root"])
        self.assertEqual(report.install_commands[0], "apt-get update")
        self.assertTrue(all(not command.startswith("sudo ") for command in report.install_commands))
        self.assertEqual(report.fallback_install_commands, ["apt-get install -y firejail"])
        self.assertEqual(report.omx_optional_install_commands, ["apt-get install -y xz-utils"])
        self.assertIn("apt-get update", script)
        self.assertNotIn("sudo apt-get", script)

    def test_compile_env_bootstrap_warns_when_non_root_without_sudo(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/apt-get" if name == "apt-get" else None

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=1000), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)
            self.assertTrue(report.bootstrap_script_path)
            script = Path(report.bootstrap_script_path).read_text(encoding="utf-8")

        self.assertFalse(report.install_context["is_root"])
        self.assertFalse(report.install_context["sudo_available"])
        self.assertEqual(report.install_commands, [])
        self.assertTrue(any("root privileges" in note and "sudo is not available" in note for note in report.notes))
        self.assertIn("requires root privileges or sudo", script)

    def test_compile_env_bootstrap_keeps_brew_user_space_commands_without_sudo(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/opt/homebrew/bin/brew" if name == "brew" else None

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=1000), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)

        self.assertFalse(report.install_context["is_root"])
        self.assertFalse(report.install_context["sudo_available"])
        self.assertEqual(report.install_commands[0], "brew install --cask mactex-no-gui || brew install basictex")
        self.assertTrue(all(not command.startswith("sudo ") for command in report.install_commands))

    def test_compile_env_bootstrap_uses_sudo_when_available(self) -> None:
        def fake_which(name: str) -> str | None:
            return {
                "apt-get": "/usr/bin/apt-get",
                "sudo": "/usr/bin/sudo",
            }.get(name)

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            self.assertEqual(command, ["/usr/bin/sudo", "-n", "true"])
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp, patch("paperorchestra.compile_env.os.geteuid", return_value=1000), patch(
            "paperorchestra.compile_env.shutil.which", side_effect=fake_which
        ), patch("paperorchestra.compile_env.subprocess.run", side_effect=fake_run):
            report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)

        self.assertTrue(report.install_context["sudo_available"])
        self.assertTrue(report.install_context["sudo_usable"])
        self.assertTrue(report.install_context["can_run_install_commands_directly"])
        self.assertEqual(report.install_commands[0], "sudo apt-get update")
        self.assertEqual(report.fallback_install_commands, ["sudo apt-get install -y firejail"])
        self.assertEqual(report.omx_optional_install_commands, ["sudo apt-get install -y xz-utils"])

    def test_sandbox_detection_skips_installed_but_unusable_bwrap(self) -> None:
        def fake_which(name: str) -> str | None:
            return {
                "bwrap": "/usr/bin/bwrap",
                "firejail": "/usr/bin/firejail",
            }.get(name)

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            if command[0] == "/usr/bin/bwrap":
                return subprocess.CompletedProcess(
                    command,
                    1,
                    stdout="",
                    stderr=(
                        "bwrap: No permissions to create new namespace, "
                        "likely because the kernel does not allow non-privileged user namespaces."
                    ),
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            with patch("paperorchestra.compile_env.shutil.which", side_effect=fake_which), patch(
                "paperorchestra.compile_env.subprocess.run", side_effect=fake_run
            ):
                self.assertEqual(compile_env_module.detect_sandbox_tool(), "/usr/bin/firejail")
                report = compile_env_module.inspect_compile_environment(tmp, auto_configure_wrapper=False)

        self.assertEqual(report.sandbox_tool, "/usr/bin/firejail")
        self.assertTrue(any("bwrap" in note and "failed usability probe" in note for note in report.notes))
        self.assertTrue(any("Selected sandbox tool: /usr/bin/firejail" == note for note in report.notes))

    def test_sandbox_detection_rejects_unusable_sandbox_tools(self) -> None:
        def fake_which(name: str) -> str | None:
            return "/usr/bin/bwrap" if name == "bwrap" else None

        def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="namespace creation denied")

        with patch("paperorchestra.compile_env.shutil.which", side_effect=fake_which), patch(
            "paperorchestra.compile_env.subprocess.run", side_effect=fake_run
        ):
            self.assertIsNone(compile_env_module.detect_sandbox_tool())
            report = compile_env_module.inspect_compile_environment(Path("."), auto_configure_wrapper=False)

        self.assertIsNone(report.sandbox_tool)
        self.assertTrue(any("No supported sandbox tool passed runtime usability probe" in note for note in report.notes))

    def test_compile_latex_supports_tectonic_backend(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                calls = []

                def fake_which(name: str):
                    return f"/fake/{name}" if name == "tectonic" else None

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    calls.append(full_cmd)
                    (out_dir / "paper.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=fake_which), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
            self.assertTrue(report.pdf_exists)
            self.assertTrue(any("tectonic" in command for command in calls[0]))
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_opt_in_error_lists_next_commands(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        try:
            os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                with self.assertRaises(LatexBuildError) as ctx:
                    compile_latex_with_report(source, workdir=root / "out", output_log=root / "build.log")
            message = str(ctx.exception)
            self.assertIn("paperorchestra check-compile-env", message)
            self.assertIn("paperorchestra bootstrap-compile-env", message)
            self.assertIn("PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile", message)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow

    def test_compile_latex_missing_environment_error_summarizes_engine_and_sandbox(self) -> None:
        class FakeCompileReport:
            latex_engine = None
            sandbox_tool = None
            sandbox_wrapper_path = None

        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                with patch("paperorchestra.latex.ensure_sandbox_wrapper", return_value=None), patch(
                    "paperorchestra.latex.inspect_compile_environment", return_value=FakeCompileReport()
                ):
                    with self.assertRaises(LatexBuildError) as ctx:
                        compile_latex_with_report(source, workdir=root / "out", output_log=root / "build.log")
            message = str(ctx.exception)
            self.assertIn("compile environment is not ready", message)
            self.assertIn("LaTeX engine", message)
            self.assertIn("latexmk, pdflatex, or tectonic", message)
            self.assertIn("Usable sandbox", message)
            self.assertIn("PAPERO_TEX_SANDBOX_CMD", message)
            self.assertIn("paperorchestra check-compile-env", message)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_missing_engine_error_lists_recovery_commands(self) -> None:
        class FakeCompileReport:
            latex_engine = None
            sandbox_tool = "/usr/bin/firejail"
            sandbox_wrapper_path = '["/tmp/tex-sandbox.sh"]'

        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text("\\documentclass{article}\\begin{document}ok\\end{document}\n", encoding="utf-8")
                with patch("paperorchestra.latex.shutil.which", return_value=None), patch(
                    "paperorchestra.latex.inspect_compile_environment", return_value=FakeCompileReport()
                ):
                    with self.assertRaises(LatexBuildError) as ctx:
                        compile_latex_with_report(source, workdir=root / "out", output_log=root / "build.log")
            message = str(ctx.exception)
            self.assertIn("compile environment is not ready", message)
            self.assertIn("LaTeX engine: latexmk, pdflatex, or tectonic", message)
            self.assertIn("Usable sandbox: /usr/bin/firejail", message)
            self.assertIn("paperorchestra check-compile-env", message)
            self.assertIn("paperorchestra bootstrap-compile-env", message)
            self.assertIn("PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile", message)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_latex_wrapped_command_timeout_defaults_to_30_seconds(self) -> None:
        old_timeout = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC")
        try:
            os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            with patch("paperorchestra.latex.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["latexmk"], 0, stdout=b"", stderr=b"")
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
        finally:
            if old_timeout is None:
                os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            else:
                os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = old_timeout

    def test_latex_wrapped_command_uses_configured_timeout(self) -> None:
        old_timeout = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC")
        try:
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "120"
            with patch("paperorchestra.latex.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(["latexmk"], 0, stdout=b"", stderr=b"")
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            self.assertEqual(run.call_args.kwargs["timeout"], 120)
        finally:
            if old_timeout is None:
                os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            else:
                os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = old_timeout

    def test_latex_wrapped_command_rejects_invalid_timeout(self) -> None:
        old_timeout = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC")
        try:
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "not-a-number"
            with self.assertRaisesRegex(LatexBuildError, "PAPERO_LATEX_TIMEOUT_SEC"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "0"
            with self.assertRaisesRegex(LatexBuildError, "between 1 and 3600"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "nan"
            with self.assertRaisesRegex(LatexBuildError, "finite number"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
            os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = "inf"
            with self.assertRaisesRegex(LatexBuildError, "finite number"):
                _run_wrapped_command(["latexmk"], env={}, cwd=Path.cwd())
        finally:
            if old_timeout is None:
                os.environ.pop("PAPERO_LATEX_TIMEOUT_SEC", None)
            else:
                os.environ["PAPERO_LATEX_TIMEOUT_SEC"] = old_timeout

    def test_compile_latex_sets_bib_and_bst_search_paths(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        old_texinputs = os.environ.get("TEXINPUTS")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            os.environ["TEXINPUTS"] = "/tmp/custom-bst:"
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\nX\\bibliographystyle{IEEEtran}\\bibliography{references}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "references.bib").write_text("@article{a,title={A},author={B},year={2024}}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                seen_env = {}

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    seen_env.update(env)
                    (out_dir / "paper.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "latexmk" else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
            self.assertIn(str(out_dir), seen_env["BIBINPUTS"])
            self.assertIn(str(root), seen_env["BIBINPUTS"])
            self.assertIn("/tmp/custom-bst", seen_env["BSTINPUTS"])
            self.assertTrue(seen_env["BSTINPUTS"].endswith(os.pathsep))
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox
            if old_texinputs is None:
                os.environ.pop("TEXINPUTS", None)
            else:
                os.environ["TEXINPUTS"] = old_texinputs

    def test_compile_latex_copies_safe_relative_bibliographies(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / ".paper-orchestra" / "runs" / "po-demo" / "artifacts" / "paper.full.tex"
                source.parent.mkdir(parents=True)
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "X\\bibliographystyle{plain}\\bibliography { inputs/reference_metadata_seed, inputs/custom_seed }\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "inputs").mkdir()
                (root / "inputs" / "reference_metadata_seed.bib").write_text(
                    "@article{a,title={A},author={B},year={2024}}\n",
                    encoding="utf-8",
                )
                (root / "inputs" / "custom_seed.bib").write_text(
                    "@article{c,title={C},author={D},year={2025}}\n",
                    encoding="utf-8",
                )
                out_dir = source.parent.parent / "build"
                log = source.parent.parent / "latex-build.log"

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    for name in ["reference_metadata_seed.bib", "custom_seed.bib"]:
                        self.assertTrue(
                            (out_dir / "inputs" / name).exists(),
                            "compile workdir should preserve safe bibliography paths emitted in \\bibliography{...}",
                        )
                    self.assertIn(str(out_dir), env["BIBINPUTS"])
                    (out_dir / "paper.full.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.full.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "latexmk" else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
            self.assertTrue(report.pdf_exists)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_does_not_copy_unsafe_bibliography_paths_or_symlinks(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / ".paper-orchestra" / "runs" / "po-demo" / "artifacts" / "paper.full.tex"
                source.parent.mkdir(parents=True)
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "\\bibliographystyle{plain}\\bibliography{../secret,/tmp/secret,inputs/symlinked_seed,linked_inputs/parent_seed}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "inputs").mkdir()
                outside = root.parent / f"{root.name}-outside.bib"
                outside.write_text("@article{x,title={X}}\n", encoding="utf-8")
                (root / "inputs" / "symlinked_seed.bib").symlink_to(outside)
                real_inputs = root / "real_inputs"
                real_inputs.mkdir()
                (real_inputs / "parent_seed.bib").write_text("@article{p,title={P}}\n", encoding="utf-8")
                (root / "linked_inputs").symlink_to(real_inputs, target_is_directory=True)
                out_dir = source.parent.parent / "build"
                log = source.parent.parent / "latex-build.log"

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    self.assertFalse((out_dir / "secret.bib").exists())
                    self.assertFalse((out_dir / "tmp" / "secret.bib").exists())
                    self.assertFalse((out_dir / "inputs" / "symlinked_seed.bib").exists())
                    self.assertFalse((out_dir / "linked_inputs" / "parent_seed.bib").exists())
                    (out_dir / "paper.full.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.full.pdf").write_bytes(b"%PDF-1.5\n")
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name == "latexmk" else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertTrue(report.clean)
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_forces_latexmk_rerun_after_bibtex_and_reference_recovery(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\nX\\bibliographystyle{plain}\\bibliography{references}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "references.bib").write_text("@article{a,title={A},author={B},year={2024}}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                calls = []

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    calls.append(list(full_cmd))
                    (out_dir / "paper.pdf").parent.mkdir(parents=True, exist_ok=True)
                    (out_dir / "paper.pdf").write_bytes(b"%PDF-1.5\n")
                    if "bibtex" in full_cmd:
                        return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")
                    return subprocess.CompletedProcess(
                        full_cmd,
                        0,
                        stdout=b"undefined citations detected\nundefined reference\n",
                        stderr=b"",
                    )

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name in {"latexmk", "bibtex"} else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    compile_latex_with_report(source, workdir=out_dir, output_log=log)
            latexmk_calls = [call for call in calls if "latexmk" in call]
            self.assertTrue(any("-g" in call for call in latexmk_calls[1:]))
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox

    def test_compile_latex_does_not_report_citations_from_reference_summary_heading(self) -> None:
        old_allow = os.environ.get("PAPERO_ALLOW_TEX_COMPILE")
        old_sandbox = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        try:
            os.environ["PAPERO_ALLOW_TEX_COMPILE"] = "1"
            os.environ["PAPERO_TEX_SANDBOX_CMD"] = '["sandbox"]'
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "paper.tex"
                source.write_text(
                    "\\documentclass{article}\n\\begin{document}\n"
                    "See Section~\\ref{sec:missing} and prior work~\\cite{a}."
                    "\\bibliographystyle{plain}\\bibliography{references}\\end{document}\n",
                    encoding="utf-8",
                )
                (root / "references.bib").write_text("@article{a,title={A},author={B},year={2024}}\n", encoding="utf-8")
                out_dir = root / "out"
                log = root / "build.log"
                latexmk_outputs = [
                    b"undefined citations detected\nundefined reference\n",
                    b"Latexmk: ====Undefined refs and citations with line #s in .tex file:\n"
                    b"  Reference `sec:missing' on page 1 undefined on input line 2\n"
                    b"Latexmk: Summary of warnings from last run of *latex:\n"
                    b"  Latex failed to resolve 1 reference(s)\n",
                    b"Latexmk: ====Undefined refs and citations with line #s in .tex file:\n"
                    b"  Reference `sec:missing' on page 1 undefined on input line 2\n"
                    b"Latexmk: Summary of warnings from last run of *latex:\n"
                    b"  Latex failed to resolve 1 reference(s)\n",
                ]

                def fake_run(full_cmd, *, env, cwd, timeout=30):
                    calls_pdf = out_dir / "paper.pdf"
                    calls_pdf.parent.mkdir(parents=True, exist_ok=True)
                    calls_pdf.write_bytes(b"%PDF-1.5\n")
                    if "bibtex" in full_cmd:
                        return subprocess.CompletedProcess(full_cmd, 0, stdout=b"", stderr=b"")
                    output = latexmk_outputs.pop(0)
                    return subprocess.CompletedProcess(full_cmd, 0, stdout=output, stderr=b"")

                with patch("paperorchestra.latex.shutil.which", side_effect=lambda name: f"/fake/{name}" if name in {"latexmk", "bibtex"} else None), patch(
                    "paperorchestra.latex._run_wrapped_command", side_effect=fake_run
                ):
                    report = compile_latex_with_report(source, workdir=out_dir, output_log=log)
            self.assertEqual(report.warning_summary, ["undefined references detected"])
        finally:
            if old_allow is None:
                os.environ.pop("PAPERO_ALLOW_TEX_COMPILE", None)
            else:
                os.environ["PAPERO_ALLOW_TEX_COMPILE"] = old_allow
            if old_sandbox is None:
                os.environ.pop("PAPERO_TEX_SANDBOX_CMD", None)
            else:
                os.environ["PAPERO_TEX_SANDBOX_CMD"] = old_sandbox
