from __future__ import annotations

from pathlib import Path

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine.section_writing_prompt import build_section_writing_plan
from paperorchestra.manuscript.narrative import write_planning_artifacts


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def _seed_section_prompt_session(tmp_path: Path):
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=_write(tmp_path / "idea.md", "The method is an evidence-grounded writing pipeline."),
            experimental_log_path=_write(tmp_path / "experimental.md", "Evaluation results are qualitative."),
            template_path=_write(
                tmp_path / "template.tex",
                r"""\documentclass{article}
\begin{document}
\section{Introduction}
Template intro.
\section{Method}
Template method.
\section{Experiments}
Template experiments.
\end{document}
""",
            ),
            guidelines_path=_write(tmp_path / "guidelines.md", "Use compact scholarly prose."),
        ),
    )
    outline_path = artifact_path(tmp_path, "outline.json")
    citation_path = artifact_path(tmp_path, "citation_map.json")
    write_json(
        outline_path,
        {
            "section_plan": [
                {"section_title": "Introduction"},
                {"section_title": "Method"},
                {"section_title": "Experiments"},
            ]
        },
    )
    write_json(
        citation_path,
        {"smith2024": {"title": "Grounded Writing", "authors": ["A. Smith"], "year": 2024}},
    )
    state.artifacts.outline_json = str(outline_path)
    state.artifacts.citation_map_json = str(citation_path)
    save_session(tmp_path, state)
    write_planning_artifacts(tmp_path)
    return load_session(tmp_path)


def test_selected_section_rewrite_requires_existing_paper(tmp_path: Path) -> None:
    state = _seed_section_prompt_session(tmp_path)

    with pytest.raises(ContractError, match="existing paper.full.tex"):
        build_section_writing_plan(tmp_path, state, selected_sections=["Method"], claim_safe=False)


def test_selected_section_plan_scopes_prompt_and_contexts_to_existing_section(tmp_path: Path) -> None:
    state = _seed_section_prompt_session(tmp_path)
    paper_path = artifact_path(tmp_path, "paper.full.tex")
    paper_path.write_text(
        r"""\documentclass{article}
\begin{document}
\section{Introduction}
Existing intro with \cite{smith2024}.
\section{Method}
Existing method skeleton with \cite{smith2024}.
\section{Experiments}
Existing experiments should stay outside the rewrite prompt.
\end{document}
""",
        encoding="utf-8",
    )
    state.artifacts.paper_full_tex = str(paper_path)
    save_session(tmp_path, state)

    plan = build_section_writing_plan(tmp_path, state, selected_sections=["Method"], claim_safe=False)

    assert plan.selected_sections == ["Method"]
    assert plan.current_source == paper_path.read_text(encoding="utf-8")
    assert plan.validation_context.selected_sections == ["Method"]
    assert plan.validation_context.expected_section_titles == ["Method"]
    assert "Rewrite ONLY these sections: Method" in plan.user_prompt
    assert "&quot;only_sections&quot;" in plan.user_prompt
    assert "&quot;Method&quot;" in plan.user_prompt
    assert "Existing method skeleton" in plan.draft_context.template_content
    assert "Existing experiments should stay outside" not in plan.draft_context.template_content
    assert "Existing experiments should stay outside" not in plan.user_prompt
