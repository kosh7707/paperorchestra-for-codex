from __future__ import annotations

import html
from pathlib import Path

from paperorchestra.engine import prior_work_prompt


def test_prior_work_context_collects_paper_bib_and_artifact_materials(tmp_path: Path) -> None:
    paper = tmp_path / "paper.full.tex"
    paper.write_text("\\section{Intro}", encoding="utf-8")
    (tmp_path / "references.bib").write_text("@inproceedings{Key}", encoding="utf-8")
    repo = tmp_path / "artifact"
    (repo / "benchmarks").mkdir(parents=True)
    (repo / "README.md").write_text("artifact readme", encoding="utf-8")
    (repo / "benchmarks" / "DATA_FORMAT.md").write_text("data schema", encoding="utf-8")

    context = prior_work_prompt.build_prior_work_context_from_paths(paper, repo)

    assert '<DATA_BLOCK name="source_paper.tex">' in context
    assert html.escape("\\section{Intro}") in context
    assert '<DATA_BLOCK name="source_references.bib">' in context
    assert '<DATA_BLOCK name="artifact_repo/README.md">' in context
    assert '<DATA_BLOCK name="artifact_repo/benchmarks/DATA_FORMAT.md">' in context
    assert "benchmarks/result.txt" not in context


def test_build_prior_work_seed_prompts_preserves_contract_blocks(tmp_path: Path) -> None:
    source_paper = tmp_path / "source.tex"
    source_paper.write_text("source paper", encoding="utf-8")

    prompts = prior_work_prompt.build_prior_work_seed_prompts(
        {
            "idea": "agentic SAST alert triage",
            "experimental_log": "recall-preserving results",
            "guidelines": "LNCS",
        },
        cutoff_date="2026-01-01",
        source="codex_web_seed",
        paper=source_paper,
        artifact_repo=None,
    )

    assert '<DATA_BLOCK name="idea.md">' in prompts.user_prompt
    assert '<DATA_BLOCK name="experimental_log.md">' in prompts.user_prompt
    assert '<DATA_BLOCK name="conference_guidelines.md">' in prompts.user_prompt
    assert '<DATA_BLOCK name="cutoff_date">' in prompts.user_prompt
    assert '<DATA_BLOCK name="source_paper.tex">' in prompts.user_prompt
    assert "Produce a curated prior_work seed JSON" in prompts.user_prompt
    assert "source='codex_web_seed'" in prompts.system_prompt
    assert "Do not fabricate bibliographic metadata" in prompts.system_prompt
