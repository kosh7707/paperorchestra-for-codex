from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from paperorchestra.manuscript.latex_models import CompileResult


@dataclass
class LatexCompileRun:
    source: str | Path
    workdir: str | Path
    output_log: str | Path
    stage: Any
    source_path: Path = field(init=False)
    workdir_path: Path = field(init=False)
    log_path: Path = field(init=False)
    manuscript_bytes: bytes = field(init=False)
    manuscript_sha256: str = field(init=False)
    sandbox_command: str = field(init=False)
    run_root: Path = field(init=False)
    full_cmd: list[str] = field(init=False)
    env: dict[str, str] = field(init=False)
    proc: Any = field(init=False)
    log_text: str = field(init=False, default="")
    pdf_path: Path = field(init=False)
    pdf_exists: bool = field(init=False, default=False)
    pdf_sha256: str | None = field(init=False, default=None)
    warning_summary: Any = field(init=False, default_factory=list)

    def run(self) -> CompileResult:
        self._initialize_paths_and_source()
        self._resolve_sandbox()
        self._prepare_inputs()
        self._build_command_and_environment()
        self._run_initial_compile()
        self._run_recovery_passes()
        self.log_path.write_text(self.log_text, encoding="utf-8")
        return self._result()

    def _initialize_paths_and_source(self) -> None:
        if self.stage.os.environ.get("PAPERO_ALLOW_TEX_COMPILE") != "1":
            raise self.stage.LatexBuildError(self.stage.compile_opt_in_error_message())
        self.sandbox_command = self.stage.os.environ.get("PAPERO_TEX_SANDBOX_CMD")
        self.source_path = Path(self.source).resolve()
        self.manuscript_bytes = self.source_path.read_bytes()
        self.manuscript_sha256 = self.stage.hashlib.sha256(self.manuscript_bytes).hexdigest()
        self.workdir_path = Path(self.workdir).resolve()
        self.workdir_path.mkdir(parents=True, exist_ok=True)
        self.log_path = Path(self.output_log).resolve()

    def _resolve_sandbox(self) -> None:
        if self.sandbox_command:
            return
        project_root = self.stage._infer_project_root_from_source(self.source_path)
        wrapper = self.stage.ensure_sandbox_wrapper(project_root)
        if wrapper:
            self.sandbox_command = f'["{wrapper}"]'
            return
        raise self.stage.LatexBuildError(
            self.stage.missing_compile_environment_message(project_root, self.stage.inspect_compile_environment)
        )

    def _prepare_inputs(self) -> None:
        source_text = self.manuscript_bytes.decode("utf-8")
        self.stage.validate_latex_source(source_text)
        self.stage._prepare_compile_inputs(self.source_path, self.workdir_path)
        self.run_root = self.stage._infer_run_root_from_source(self.source_path)
        self.stage._copy_bibliography_input_files(
            bibliography_stems=self.stage._referenced_bibliography_stems(source_text),
            source_path=self.source_path,
            run_root=self.run_root,
            workdir_path=self.workdir_path,
        )

    def _build_command_and_environment(self) -> None:
        source_arg = self.stage.os.path.relpath(self.source_path, self.run_root)
        output_dir_arg = self.stage.os.path.relpath(self.workdir_path, self.run_root)
        self.full_cmd = self.stage._parse_sandbox_command(self.sandbox_command) + self._engine_command(
            source_arg,
            output_dir_arg,
        )
        self.env = self.stage.os.environ.copy()
        self.env["openin_any"] = "p"
        self.env["openout_any"] = "p"
        self.stage._prepend_path(self.env, "BIBINPUTS", self.workdir_path, self.source_path.parent)
        self.stage._prepend_path(self.env, "BSTINPUTS", *self._bst_candidates())

    def _engine_command(self, source_arg: str, output_dir_arg: str) -> list[str]:
        if self.stage.shutil.which("latexmk"):
            return ["latexmk", "-pdf", "-f", "-interaction=nonstopmode", f"-output-directory={output_dir_arg}", source_arg]
        if self.stage.shutil.which("pdflatex"):
            return ["pdflatex", "-interaction=nonstopmode", f"-output-directory={output_dir_arg}", source_arg]
        if self.stage.shutil.which("tectonic"):
            return ["tectonic", "--keep-logs", "--keep-intermediates", "--outdir", output_dir_arg, source_arg]
        raise self.stage.LatexBuildError(
            self.stage.missing_compile_environment_message(
                self.stage._infer_project_root_from_source(self.source_path),
                self.stage.inspect_compile_environment,
            )
        )

    def _bst_candidates(self) -> list[Path]:
        candidates = [self.source_path.parent]
        for raw in self.env.get("TEXINPUTS", "").split(self.stage.os.pathsep):
            raw = raw.strip()
            if raw:
                candidates.append(Path(raw.rstrip(self.stage.os.sep)))
        return candidates

    def _run_initial_compile(self) -> None:
        self.proc = self.stage._run_wrapped_command(self.full_cmd, env=self.env, cwd=self.run_root)
        self.log_text = self.proc.stdout.decode("utf-8", errors="replace")
        self._refresh_pdf_state()

    def _run_recovery_passes(self) -> None:
        output_dir_arg = self.stage.os.path.relpath(self.workdir_path, self.run_root)
        if "undefined citations detected" in self.warning_summary and self.stage.shutil.which("bibtex"):
            bibtex_target = self.stage.os.path.join(output_dir_arg, self.source_path.stem)
            bibtex_cmd = self.stage._parse_sandbox_command(self.sandbox_command) + ["bibtex", bibtex_target]
            bibtex_proc = self.stage._run_wrapped_command(bibtex_cmd, env=self.env, cwd=self.run_root)
            self.log_text += "\n\n[BIBTEX RECOVERY PASS]\n" + bibtex_proc.stdout.decode("utf-8", errors="replace")
            self.proc = self.stage._run_wrapped_command(
                self.stage._force_latexmk_rerun_command(self.full_cmd),
                env=self.env,
                cwd=self.run_root,
            )
            self.log_text += "\n\n[POST-BIBTEX LATEXMK PASS]\n" + self.proc.stdout.decode("utf-8", errors="replace")
            self._refresh_pdf_state()

        if "undefined references detected" in self.warning_summary and self.pdf_exists:
            self.proc = self.stage._run_wrapped_command(
                self.stage._force_latexmk_rerun_command(self.full_cmd),
                env=self.env,
                cwd=self.run_root,
            )
            self.log_text += "\n\n[REFERENCE STABILIZATION PASS]\n" + self.proc.stdout.decode(
                "utf-8",
                errors="replace",
            )
            self._refresh_pdf_state()

    def _refresh_pdf_state(self) -> None:
        self.pdf_path = self.workdir_path / self.source_path.with_suffix(".pdf").name
        self.pdf_exists = self.pdf_path.exists()
        self.pdf_sha256 = self.stage.hashlib.sha256(self.pdf_path.read_bytes()).hexdigest() if self.pdf_exists else None
        self.warning_summary = self.stage._summarize_compile_warnings(self.log_text)

    def _result(self) -> CompileResult:
        clean = self.proc.returncode == 0 and self.pdf_exists and not self.warning_summary
        return CompileResult(
            pdf_path=str(self.pdf_path) if self.pdf_exists else None,
            log_path=str(self.log_path),
            source_path=str(self.source_path),
            manuscript_sha256=self.manuscript_sha256,
            pdf_sha256=self.pdf_sha256,
            return_code=self.proc.returncode,
            pdf_exists=self.pdf_exists,
            clean=clean,
            warning_summary=self.warning_summary,
        )


__all__ = ["LatexCompileRun"]
