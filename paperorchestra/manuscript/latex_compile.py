from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from paperorchestra.runtime.compile_env import ensure_sandbox_wrapper, inspect_compile_environment
from paperorchestra.manuscript.latex_commands import (
    _parse_sandbox_command,
    _run_wrapped_command,
    _summarize_compile_warnings,
)
from paperorchestra.manuscript.latex_inputs import (
    _copy_bibliography_input_files,
    _force_latexmk_rerun_command,
    _infer_project_root_from_source,
    _infer_run_root_from_source,
    _prepare_compile_inputs,
    _prepend_path,
    _referenced_bibliography_stems,
)
from paperorchestra.manuscript.latex_messages import compile_opt_in_error_message, missing_compile_environment_message
from paperorchestra.manuscript.latex_models import CompileResult, LatexBuildError
from paperorchestra.manuscript.latex_safety import blocked_latex_pattern


def validate_latex_source(source_text: str) -> None:
    blocked_pattern = blocked_latex_pattern(source_text)
    if blocked_pattern:
        raise LatexBuildError(f"LaTeX source contains a blocked pattern: {blocked_pattern}")


def compile_latex_with_report(source: str | Path, *, workdir: str | Path, output_log: str | Path) -> CompileResult:
    if os.environ.get("PAPERO_ALLOW_TEX_COMPILE") != "1":
        raise LatexBuildError(compile_opt_in_error_message())
    sandbox_command = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
    source_path = Path(source).resolve()
    manuscript_bytes = source_path.read_bytes()
    manuscript_sha256 = hashlib.sha256(manuscript_bytes).hexdigest()
    if not sandbox_command:
        wrapper = ensure_sandbox_wrapper(_infer_project_root_from_source(source_path))
        if wrapper:
            sandbox_command = f'["{wrapper}"]'
        else:
            raise LatexBuildError(missing_compile_environment_message(_infer_project_root_from_source(source_path), inspect_compile_environment))
    workdir_path = Path(workdir).resolve()
    workdir_path.mkdir(parents=True, exist_ok=True)
    log_path = Path(output_log).resolve()
    source_text = manuscript_bytes.decode("utf-8")
    validate_latex_source(source_text)
    _prepare_compile_inputs(source_path, workdir_path)
    run_root = _infer_run_root_from_source(source_path)
    bibliography_stems = _referenced_bibliography_stems(source_text)
    _copy_bibliography_input_files(
        bibliography_stems=bibliography_stems,
        source_path=source_path,
        run_root=run_root,
        workdir_path=workdir_path,
    )
    source_arg = os.path.relpath(source_path, run_root)
    output_dir_arg = os.path.relpath(workdir_path, run_root)

    if shutil.which("latexmk"):
        cmd = [
            "latexmk",
            "-pdf",
            "-f",
            "-interaction=nonstopmode",
            f"-output-directory={output_dir_arg}",
            source_arg,
        ]
    elif shutil.which("pdflatex"):
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            f"-output-directory={output_dir_arg}",
            source_arg,
        ]
    elif shutil.which("tectonic"):
        cmd = [
            "tectonic",
            "--keep-logs",
            "--keep-intermediates",
            "--outdir",
            output_dir_arg,
            source_arg,
        ]
    else:
        raise LatexBuildError(missing_compile_environment_message(_infer_project_root_from_source(source_path), inspect_compile_environment))

    env = os.environ.copy()
    env["openin_any"] = "p"
    env["openout_any"] = "p"
    _prepend_path(env, "BIBINPUTS", workdir_path, source_path.parent)
    bst_candidates: list[Path] = [source_path.parent]
    texinputs = env.get("TEXINPUTS", "")
    for raw in texinputs.split(os.pathsep):
        raw = raw.strip()
        if not raw:
            continue
        bst_candidates.append(Path(raw.rstrip(os.sep)))
    _prepend_path(env, "BSTINPUTS", *bst_candidates)
    full_cmd = _parse_sandbox_command(sandbox_command) + cmd
    proc = _run_wrapped_command(full_cmd, env=env, cwd=run_root)
    log_text = proc.stdout.decode("utf-8", errors="replace")
    pdf_name = source_path.with_suffix(".pdf").name
    pdf_path = workdir_path / pdf_name
    pdf_exists = pdf_path.exists()
    pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_exists else None
    warning_summary = _summarize_compile_warnings(log_text)

    if "undefined citations detected" in warning_summary and shutil.which("bibtex"):
        bibtex_target = os.path.join(output_dir_arg, source_path.stem)
        bibtex_cmd = _parse_sandbox_command(sandbox_command) + ["bibtex", bibtex_target]
        bibtex_proc = _run_wrapped_command(bibtex_cmd, env=env, cwd=run_root)
        log_text += "\n\n[BIBTEX RECOVERY PASS]\n" + bibtex_proc.stdout.decode("utf-8", errors="replace")
        proc = _run_wrapped_command(_force_latexmk_rerun_command(full_cmd), env=env, cwd=run_root)
        log_text += "\n\n[POST-BIBTEX LATEXMK PASS]\n" + proc.stdout.decode("utf-8", errors="replace")
        pdf_exists = pdf_path.exists()
        pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_exists else None
        warning_summary = _summarize_compile_warnings(log_text)

    if "undefined references detected" in warning_summary and pdf_exists:
        proc = _run_wrapped_command(_force_latexmk_rerun_command(full_cmd), env=env, cwd=run_root)
        log_text += "\n\n[REFERENCE STABILIZATION PASS]\n" + proc.stdout.decode("utf-8", errors="replace")
        pdf_exists = pdf_path.exists()
        pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_exists else None
        warning_summary = _summarize_compile_warnings(log_text)

    log_path.write_text(log_text, encoding="utf-8")
    clean = proc.returncode == 0 and pdf_exists and not warning_summary
    return CompileResult(
        pdf_path=str(pdf_path) if pdf_exists else None,
        log_path=str(log_path),
        source_path=str(source_path),
        manuscript_sha256=manuscript_sha256,
        pdf_sha256=pdf_sha256,
        return_code=proc.returncode,
        pdf_exists=pdf_exists,
        clean=clean,
        warning_summary=warning_summary,
    )


def compile_latex(source: str | Path, *, workdir: str | Path, output_log: str | Path) -> Path:
    report = compile_latex_with_report(source, workdir=workdir, output_log=output_log)
    if not report.pdf_exists:
        raise LatexBuildError(f"LaTeX build failed. See log: {report.log_path}")
    if not report.clean:
        raise LatexBuildError(f"LaTeX build completed with unresolved issues. See log: {report.log_path}")
    return Path(report.pdf_path)
