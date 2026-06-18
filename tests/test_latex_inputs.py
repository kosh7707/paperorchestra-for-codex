from __future__ import annotations

import os
from pathlib import Path

from paperorchestra.manuscript.latex_bibliography_inputs import (
    _copy_bibliography_input_files,
    _is_relative_bibliography_path_safe,
    _prepare_compile_inputs,
    _referenced_bibliography_stems,
)
from paperorchestra.manuscript.latex_input_env import _force_latexmk_rerun_command, _prepend_path
from paperorchestra.manuscript.latex_input_roots import _infer_project_root_from_source, _infer_run_root_from_source


def test_infer_roots_and_prepare_default_references(tmp_path: Path) -> None:
    source = tmp_path / ".paper-orchestra" / "runs" / "po-1" / "artifacts" / "paper.tex"
    source.parent.mkdir(parents=True)
    source.write_text("paper", encoding="utf-8")
    (source.parent / "references.bib").write_text("@x{a}", encoding="utf-8")
    workdir = tmp_path / "build"
    workdir.mkdir()

    assert _infer_project_root_from_source(source) == tmp_path
    assert _infer_run_root_from_source(source) == source.parent.parent
    _prepare_compile_inputs(source, workdir)
    assert (workdir / "references.bib").read_text(encoding="utf-8") == "@x{a}"


def test_referenced_bibliography_stems_are_deduped_and_path_safe() -> None:
    text = r"""
\bibliography{references, nested/extra}
\bibliography{references, ../secret, /abs/path}
"""
    assert _referenced_bibliography_stems(text) == ["references", "nested/extra", "../secret", "/abs/path"]
    assert _is_relative_bibliography_path_safe("nested/extra") is True
    assert _is_relative_bibliography_path_safe("../secret") is False
    assert _is_relative_bibliography_path_safe("/abs/path") is False


def test_copy_bibliography_inputs_searches_source_run_and_project_roots(tmp_path: Path) -> None:
    source = tmp_path / ".paper-orchestra" / "runs" / "po-1" / "artifacts" / "paper.tex"
    run_root = source.parent.parent
    source.parent.mkdir(parents=True)
    source.write_text("paper", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "project.bib").write_text("@x{project}", encoding="utf-8")
    (run_root / "runref.bib").write_text("@x{run}", encoding="utf-8")
    (source.parent / "local.bib").write_text("@x{local}", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()

    _copy_bibliography_input_files(
        bibliography_stems=["local", "runref", "nested/project", "../secret"],
        source_path=source,
        run_root=run_root,
        workdir_path=workdir,
    )

    assert (workdir / "local.bib").read_text(encoding="utf-8") == "@x{local}"
    assert (workdir / "runref.bib").read_text(encoding="utf-8") == "@x{run}"
    assert (workdir / "nested" / "project.bib").read_text(encoding="utf-8") == "@x{project}"
    assert not (workdir / ".." / "secret.bib").exists()


def test_prepend_path_and_force_latexmk_rerun_command(tmp_path: Path) -> None:
    env = {"TEXINPUTS": "existing"}
    _prepend_path(env, "TEXINPUTS", tmp_path / "a", tmp_path / "b")
    assert env["TEXINPUTS"] == os.pathsep.join([str(tmp_path / "a"), str(tmp_path / "b"), "existing"])

    empty_env: dict[str, str] = {}
    _prepend_path(empty_env, "BIBINPUTS", tmp_path / "bib")
    assert empty_env["BIBINPUTS"] == str(tmp_path / "bib") + os.pathsep

    assert _force_latexmk_rerun_command(["wrap", "latexmk", "-pdf"]) == ["wrap", "latexmk", "-g", "-pdf"]
    assert _force_latexmk_rerun_command(["pdflatex", "paper.tex"]) == ["pdflatex", "paper.tex"]
