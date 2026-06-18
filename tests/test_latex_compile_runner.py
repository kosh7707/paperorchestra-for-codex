from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paperorchestra.manuscript import latex_compile


def test_compile_latex_with_report_builds_pdf_with_sandboxed_latexmk(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "paper.tex"
    source.write_text("\\documentclass{article}\\begin{document}Hi\\end{document}", encoding="utf-8")
    workdir = tmp_path / "build"
    pdf = workdir / "paper.pdf"
    calls: list[list[str]] = []

    monkeypatch.setenv("PAPERO_ALLOW_TEX_COMPILE", "1")
    monkeypatch.setenv("PAPERO_TEX_SANDBOX_CMD", '["sandbox"]')
    monkeypatch.setattr(latex_compile.shutil, "which", lambda name: "/usr/bin/latexmk" if name == "latexmk" else None)
    monkeypatch.setattr(latex_compile, "_parse_sandbox_command", lambda raw: ["sandbox"])
    monkeypatch.setattr(latex_compile, "_prepare_compile_inputs", lambda source_path, workdir_path: workdir_path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(latex_compile, "_referenced_bibliography_stems", lambda source_text: [])
    monkeypatch.setattr(latex_compile, "_copy_bibliography_input_files", lambda **kwargs: None)
    monkeypatch.setattr(latex_compile, "_infer_run_root_from_source", lambda source_path: tmp_path)
    monkeypatch.setattr(latex_compile, "_summarize_compile_warnings", lambda log_text: [])

    def run(cmd, *, env, cwd):
        calls.append(cmd)
        pdf.write_bytes(b"pdf")
        return SimpleNamespace(stdout=b"ok", returncode=0)

    monkeypatch.setattr(latex_compile, "_run_wrapped_command", run)

    report = latex_compile.compile_latex_with_report(source, workdir=workdir, output_log=tmp_path / "compile.log")

    assert calls == [
        [
            "sandbox",
            "latexmk",
            "-pdf",
            "-f",
            "-interaction=nonstopmode",
            "-output-directory=build",
            "paper.tex",
        ]
    ]
    assert report.pdf_exists is True
    assert report.clean is True
    assert Path(report.log_path).read_text(encoding="utf-8") == "ok"


def test_compile_latex_with_report_runs_bibtex_recovery_when_needed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "paper.tex"
    source.write_text("\\documentclass{article}\\begin{document}\\cite{x}\\end{document}", encoding="utf-8")
    workdir = tmp_path / "build"
    pdf = workdir / "paper.pdf"
    calls: list[list[str]] = []
    warning_calls = iter([["undefined citations detected"], []])

    monkeypatch.setenv("PAPERO_ALLOW_TEX_COMPILE", "1")
    monkeypatch.setenv("PAPERO_TEX_SANDBOX_CMD", '["sandbox"]')
    monkeypatch.setattr(latex_compile.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"latexmk", "bibtex"} else None)
    monkeypatch.setattr(latex_compile, "_parse_sandbox_command", lambda raw: ["sandbox"])
    monkeypatch.setattr(latex_compile, "_prepare_compile_inputs", lambda source_path, workdir_path: workdir_path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(latex_compile, "_referenced_bibliography_stems", lambda source_text: ["refs"])
    monkeypatch.setattr(latex_compile, "_copy_bibliography_input_files", lambda **kwargs: None)
    monkeypatch.setattr(latex_compile, "_infer_run_root_from_source", lambda source_path: tmp_path)
    monkeypatch.setattr(latex_compile, "_summarize_compile_warnings", lambda log_text: next(warning_calls))
    monkeypatch.setattr(latex_compile, "_force_latexmk_rerun_command", lambda cmd: [*cmd, "-rerun"])

    def run(cmd, *, env, cwd):
        calls.append(cmd)
        pdf.write_bytes(b"pdf")
        return SimpleNamespace(stdout=(" ".join(cmd)).encode(), returncode=0)

    monkeypatch.setattr(latex_compile, "_run_wrapped_command", run)

    report = latex_compile.compile_latex_with_report(source, workdir=workdir, output_log=tmp_path / "compile.log")

    assert calls[1] == ["sandbox", "bibtex", "build/paper"]
    assert calls[2][-1] == "-rerun"
    assert "[BIBTEX RECOVERY PASS]" in Path(report.log_path).read_text(encoding="utf-8")
    assert report.clean is True
