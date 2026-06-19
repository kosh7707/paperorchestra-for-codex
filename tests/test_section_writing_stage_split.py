from __future__ import annotations

import inspect


def test_section_writing_public_stage_uses_prompt_and_repair_modules() -> None:
    from paperorchestra.engine import section_writing_stage
    from paperorchestra.engine.section_writing_plan_builder import build_section_writing_plan
    from paperorchestra.engine.section_writing_runner import SectionWritingRun
    from paperorchestra.engine.section_writing_types import SectionWritingPlan
    from paperorchestra.engine.section_writing_repair import SectionRepairResult, repair_section_draft_if_possible

    stage_source = inspect.getsource(section_writing_stage.write_sections)
    runner_source = inspect.getsource(SectionWritingRun)

    assert "SectionWritingRun(" in stage_source
    assert "build_section_writing_plan(" in runner_source
    assert "repair_section_draft_if_possible(" in runner_source
    assert SectionWritingPlan.__name__ == "SectionWritingPlan"
    assert SectionRepairResult.__name__ == "SectionRepairResult"
    assert callable(build_section_writing_plan)
    assert callable(repair_section_draft_if_possible)

from pathlib import Path

from paperorchestra.core.io import write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine.section_writing_stage import write_sections
from paperorchestra.manuscript.narrative_artifacts import write_planning_artifacts
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class _HealthySectionProvider(BaseProvider):
    name = "healthy-section-provider"

    def complete(self, request: CompletionRequest) -> str:
        body = " ".join(
            [
                "artifact-driven validation keeps generated paper prose tied to source materials and author constraints"
            ]
            * 4
        )
        return rf"""```latex
\documentclass{{article}}
\begin{{document}}
\section{{Introduction}}
{body} This introduction frames PaperOrchestra as a staged authoring engine for draft construction and review \cite{{smith2024}}.
\section{{Related Work}}
{body} Related systems motivate automated writing support while leaving citation grounding and revision control as central concerns \cite{{smith2024}}.
\section{{Method}}
{body} The method treats every draft as an artifact assembled from outline, verified references, planning records, and validation reports.
\section{{Experiments}}
{body} The evaluation section describes smoke validation qualitatively and avoids ungrounded quantitative claims.
\section{{Discussion}}
{body} The discussion records scope limits, human review boundaries, and the need for manual confirmation when source evidence is incomplete.
\section{{Conclusion}}
{body} The conclusion emphasizes that staged validation and citation-aware repair make paper authoring more auditable \cite{{smith2024}}.
\end{{document}}
```"""


def _write_text(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_write_sections_still_runs_through_public_stage_after_split(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text("<!-- paperorchestra:plan-approved -->\n", encoding="utf-8")
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=_write_text(
                tmp_path / "idea.md",
                "PaperOrchestra is an artifact-first paper authoring engine with staged validation.",
            ),
            experimental_log_path=_write_text(
                tmp_path / "experimental_log.md",
                "Experiment log: local smoke path completed without numeric claims.",
            ),
            template_path=_write_text(
                tmp_path / "template.tex",
                r"""\documentclass{article}
\begin{document}
\section{Introduction}
Placeholder.
\section{Related Work}
Placeholder.
\section{Method}
Placeholder.
\section{Experiments}
Placeholder.
\section{Discussion}
Placeholder.
\section{Conclusion}
Placeholder.
\end{document}
""",
            ),
            guidelines_path=_write_text(tmp_path / "guidelines.md", "Use a standard academic paper structure."),
        ),
    )
    outline_path = artifact_path(tmp_path, "outline.json")
    write_json(
        outline_path,
        {
            "section_plan": [
                {"section_title": title}
                for title in ["Introduction", "Related Work", "Method", "Experiments", "Discussion", "Conclusion"]
            ]
        },
    )
    citation_path = artifact_path(tmp_path, "citation_map.json")
    write_json(
        citation_path,
        {"smith2024": {"title": "Artifact First Writing", "authors": ["A. Smith"], "year": 2024, "venue": "CONF"}},
    )
    state.artifacts.outline_json = str(outline_path)
    state.artifacts.citation_map_json = str(citation_path)
    save_session(tmp_path, state)
    write_planning_artifacts(tmp_path)

    output = write_sections(tmp_path, _HealthySectionProvider())

    refreshed = load_session(tmp_path)
    assert output.exists()
    assert refreshed.current_phase == "iterative_content_refinement"
    assert refreshed.artifacts.paper_full_tex == str(output)
    assert refreshed.artifacts.latest_validation_json is not None
    assert "\\cite{smith2024}" in output.read_text(encoding="utf-8")
