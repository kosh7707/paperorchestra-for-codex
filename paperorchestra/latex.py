from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .compile_env import ensure_sandbox_wrapper, inspect_compile_environment


class LatexBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompileResult:
    pdf_path: str | None
    log_path: str
    source_path: str
    manuscript_sha256: str
    pdf_sha256: str | None
    return_code: int
    pdf_exists: bool
    clean: bool
    warning_summary: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


DANGEROUS_TEX_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\\write18",
        r"\\openout",
        r"\\readline",
        r"\\input\s*/",
        r"\\include\s*/",
        r"\\usepackage\s*\{shellesc\}",
        r"\\immediate\s*\\write",
    ]
]


def validate_latex_source(source_text: str) -> None:
    for pattern in DANGEROUS_TEX_PATTERNS:
        if pattern.search(source_text):
            raise LatexBuildError(f"LaTeX source contains a blocked pattern: {pattern.pattern}")


def _parse_sandbox_command(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        raise LatexBuildError("PAPERO_TEX_SANDBOX_CMD must not be empty.")
    if raw.startswith("["):
        import json

        parsed = json.loads(raw)
        if not isinstance(parsed, list) or not parsed or not all(isinstance(item, str) for item in parsed):
            raise LatexBuildError("PAPERO_TEX_SANDBOX_CMD JSON must be a non-empty string array.")
        return parsed
    return shlex.split(raw)


def _infer_project_root_from_source(source_path: Path) -> Path:
    for parent in source_path.parents:
        if parent.name == ".paper-orchestra":
            return parent.parent
    return source_path.parent


def _infer_run_root_from_source(source_path: Path) -> Path:
    for parent in source_path.parents:
        if parent.name == "artifacts":
            return parent.parent
    return source_path.parent


def _compile_opt_in_error_message() -> str:
    return """LaTeX compilation is disabled by default.

To inspect whether this machine can compile:
  paperorchestra check-compile-env

To install missing tools:
  paperorchestra bootstrap-compile-env

To intentionally compile:
  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"""


def _missing_compile_environment_message(project_root: Path) -> str:
    try:
        report = inspect_compile_environment(project_root, auto_configure_wrapper=False)
    except Exception as exc:
        return (
            "compile environment is not ready.\n\n"
            f"Could not inspect compile environment automatically: {type(exc).__name__}: {exc}\n\n"
            "Run:\n"
            "  paperorchestra check-compile-env\n"
            "  paperorchestra bootstrap-compile-env\n"
            "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"
        )

    sandbox_state = report.sandbox_tool or "missing (bwrap/firejail/nsjail or PAPERO_TEX_SANDBOX_CMD)"
    wrapper_state = report.sandbox_wrapper_path or "not configured"
    engine_state = report.latex_engine or "missing (latexmk/pdflatex/tectonic)"
    missing: list[str] = []
    if not report.latex_engine:
        missing.append("LaTeX engine: latexmk, pdflatex, or tectonic")
    if not report.sandbox_wrapper_path:
        missing.append("usable sandbox wrapper: bwrap, firejail, nsjail, or PAPERO_TEX_SANDBOX_CMD")
    missing_lines = "\n".join(f"  - {item}" for item in missing) if missing else "  - compile readiness probe did not produce a sandbox wrapper"

    return (
        "compile environment is not ready.\n\n"
        "Missing:\n"
        f"{missing_lines}\n\n"
        "Detected:\n"
        f"  LaTeX engine: {engine_state}\n"
        f"  Usable sandbox: {sandbox_state}\n"
        f"  Sandbox wrapper: {wrapper_state}\n\n"
        "Run:\n"
        "  paperorchestra check-compile-env\n"
        "  paperorchestra bootstrap-compile-env\n"
        "  PAPERO_ALLOW_TEX_COMPILE=1 paperorchestra compile"
    )


def _summarize_compile_warnings(log_text: str) -> list[str]:
    if "[REFERENCE STABILIZATION PASS]" in log_text:
        log_text = log_text.split("[REFERENCE STABILIZATION PASS]", 1)[1]
    if "[POST-BIBTEX LATEXMK PASS]" in log_text:
        log_text = log_text.split("[POST-BIBTEX LATEXMK PASS]", 1)[1]
    warnings: list[str] = []
    lowered = log_text.lower()
    if "failed to resolve 1 reference" in lowered or "undefined reference" in lowered:
        warnings.append("undefined references detected")
    if (
        re.search(r"failed to resolve\s+\d+\s+citation", lowered)
        or "undefined citations" in lowered
        or "there were undefined citations" in lowered
    ):
        warnings.append("undefined citations detected")
    if "unknown graphics extension" in lowered:
        warnings.append("unknown graphics extension encountered")
    return warnings


def _latex_timeout_seconds(timeout: int | float | None = None) -> int:
    if timeout is not None:
        value = timeout
    else:
        raw = os.environ.get("PAPERO_LATEX_TIMEOUT_SEC", "").strip()
        if not raw:
            return 30
        try:
            value = float(raw)
        except ValueError as exc:
            raise LatexBuildError("PAPERO_LATEX_TIMEOUT_SEC must be a number of seconds between 1 and 3600.") from exc
    if not math.isfinite(float(value)):
        raise LatexBuildError("PAPERO_LATEX_TIMEOUT_SEC must be a finite number of seconds between 1 and 3600.")
    if value < 1 or value > 3600:
        raise LatexBuildError("PAPERO_LATEX_TIMEOUT_SEC must be between 1 and 3600 seconds.")
    return int(value)


def _run_wrapped_command(full_cmd: list[str], *, env: dict[str, str], cwd: Path, timeout: int | float | None = None) -> subprocess.CompletedProcess:
    timeout_seconds = _latex_timeout_seconds(timeout)
    try:
        return subprocess.run(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
            env=env,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired as exc:
        raise LatexBuildError(f"LaTeX build timed out after {timeout_seconds} seconds.") from exc


def _prepare_compile_inputs(source_path: Path, workdir_path: Path) -> None:
    references_source = source_path.parent / "references.bib"
    if references_source.exists():
        shutil.copy2(references_source, workdir_path / "references.bib")


def _referenced_bibliography_stems(source_text: str) -> list[str]:
    stems: list[str] = []
    for raw_group in re.findall(r"\\bibliography\s*\{([^}]+)\}", source_text):
        for raw_stem in raw_group.split(","):
            stem = raw_stem.strip()
            if stem and stem not in stems:
                stems.append(stem)
    return stems


def _is_relative_bibliography_path_safe(raw_stem: str) -> bool:
    raw_path = Path(raw_stem)
    return bool(raw_stem) and not raw_path.is_absolute() and ".." not in raw_path.parts


def _is_regular_file_within_root(candidate: Path, base: Path) -> bool:
    if candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
        return False
    try:
        relative_parts = candidate.relative_to(base).parts
    except ValueError:
        return False
    current = base
    for part in relative_parts:
        current = current / part
        if current.is_symlink():
            return False
    try:
        candidate.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _copy_bibliography_input_files(
    *,
    bibliography_stems: list[str],
    source_path: Path,
    run_root: Path,
    workdir_path: Path,
) -> None:
    search_roots = [source_path.parent, run_root]
    project_root = _infer_project_root_from_source(source_path)
    if project_root not in search_roots:
        search_roots.append(project_root)
    for raw_stem in bibliography_stems:
        if not _is_relative_bibliography_path_safe(raw_stem):
            continue
        candidate_rel = Path(f"{raw_stem}.bib")
        for base in search_roots:
            candidate = base / candidate_rel
            if _is_regular_file_within_root(candidate, base):
                destination = workdir_path / candidate_rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)
                break


def _prepend_path(env: dict[str, str], key: str, *paths: Path) -> None:
    existing = env.get(key, "")
    parts = [str(path) for path in paths if str(path)]
    if existing:
        parts.append(existing)
        env[key] = os.pathsep.join(parts)
    elif parts:
        env[key] = os.pathsep.join(parts) + os.pathsep


def _force_latexmk_rerun_command(full_cmd: list[str]) -> list[str]:
    if "latexmk" not in full_cmd:
        return list(full_cmd)
    command = list(full_cmd)
    if "-g" not in command:
        insert_at = command.index("latexmk") + 1
        command.insert(insert_at, "-g")
    return command


def compile_latex_with_report(source: str | Path, *, workdir: str | Path, output_log: str | Path) -> CompileResult:
    if os.environ.get("PAPERO_ALLOW_TEX_COMPILE") != "1":
        raise LatexBuildError(_compile_opt_in_error_message())
    sandbox_command = os.environ.get("PAPERO_TEX_SANDBOX_CMD")
    source_path = Path(source).resolve()
    manuscript_bytes = source_path.read_bytes()
    manuscript_sha256 = hashlib.sha256(manuscript_bytes).hexdigest()
    if not sandbox_command:
        wrapper = ensure_sandbox_wrapper(_infer_project_root_from_source(source_path))
        if wrapper:
            sandbox_command = f'["{wrapper}"]'
        else:
            raise LatexBuildError(_missing_compile_environment_message(_infer_project_root_from_source(source_path)))
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
        raise LatexBuildError(_missing_compile_environment_message(_infer_project_root_from_source(source_path)))

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
