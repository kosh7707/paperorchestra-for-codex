from __future__ import annotations

from pathlib import Path
from typing import Any

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine.intro_related_stage import write_intro_related
from paperorchestra.manuscript.narrative_artifacts import write_planning_artifacts
from paperorchestra.runtime.mock_provider import MockProvider
from paperorchestra.runtime.providers import BaseProvider, CompletionRequest


class SequenceProvider(BaseProvider):
    name = "sequence"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> str:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("SequenceProvider received more completion requests than expected")
        return self._responses.pop(0)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _seed_intro_related_session(tmp_path: Path, *, citation_map: dict[str, Any] | None = None) -> Path:
    idea = _write(
        tmp_path / "idea.md",
        "We propose an artifact-grounded paper-writing engine with explicit evidence gates.",
    )
    experimental = _write(
        tmp_path / "experimental.md",
        "Experiments are complete and are discussed qualitatively without provisional numbers.",
    )
    template = _write(
        tmp_path / "template.tex",
        """\\documentclass{article}
\\begin{document}
\\section{Introduction}
Old introduction.
\\section{Related Work}
Old related work.
\\section{Method}
Method skeleton stays intact.
\\end{document}
""",
    )
    guidelines = _write(tmp_path / "guidelines.md", "Use a compact LNCS-like manuscript structure.")
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=str(idea),
            experimental_log_path=str(experimental),
            template_path=str(template),
            guidelines_path=str(guidelines),
        ),
        allow_outside_workspace=True,
    )
    outline_path = artifact_path(tmp_path, "outline.json")
    citation_map_path = artifact_path(tmp_path, "citation_map.json")
    write_json(
        outline_path,
        {
            "plotting_plan": [],
            "intro_related_work_plan": {
                "introduction_strategy": {
                    "hook_hypothesis": "Artifact-grounded writing needs evidence gates.",
                    "problem_gap_hypothesis": "Autonomous drafts can under-ground citations.",
                },
                "related_work_strategy": {
                    "overview": "Position the system against paper-writing and review agents.",
                    "subsections": [],
                },
            },
            "section_plan": [
                {"section_title": "Introduction"},
                {"section_title": "Related Work"},
                {"section_title": "Method"},
            ],
        },
    )
    write_json(
        citation_map_path,
        citation_map
        or {
            "smith2020": {"title": "Grounded Writing", "year": 2020, "abstract": "Evidence-grounded writing."},
            "lee2021": {"title": "Agentic Review", "year": 2021, "abstract": "Agentic manuscript review."},
        },
    )
    state.artifacts.outline_json = str(outline_path)
    state.artifacts.citation_map_json = str(citation_map_path)
    save_session(tmp_path, state)
    write_planning_artifacts(tmp_path)
    return tmp_path


def _intro_related_latex(citation_keys: str) -> str:
    intro = (
        "The artifact-grounded paper-writing engine uses evidence gates to position the paper against verified "
        f"background and baseline literature \\cite{{{citation_keys}}}. "
        "The introduction frames manuscript drafting as a workflow that must preserve source constraints, cite only "
        "checked materials, and avoid unsupported experimental claims."
    )
    related = (
        "Related work compares paper-writing agents, review agents, and grounded citation pipelines "
        f"\\cite{{{citation_keys}}}. The comparison emphasizes verified background literature, source-aware review, "
        "and conservative orchestration under human finalization."
    )
    return f"""```latex
\\documentclass{{article}}
\\begin{{document}}
\\section{{Introduction}}
{intro}
\\section{{Related Work}}
{related}
\\section{{Method}}
Generated method placeholder.
\\end{{document}}
```"""


def _lane_notes(cwd: Path) -> list[str]:
    return read_json(artifact_path(cwd, "lane-manifest.intro_related.json"))["notes"]


def test_write_intro_related_records_artifacts_and_preserves_other_sections(tmp_path: Path) -> None:
    cwd = _seed_intro_related_session(tmp_path)

    output_path = write_intro_related(cwd, MockProvider(), allow_recoverable_contract_issues=True)

    latex = output_path.read_text(encoding="utf-8")
    state = load_session(cwd)
    assert output_path.name == "introduction_related_work.tex"
    assert state.artifacts.intro_related_tex == str(output_path)
    assert state.current_phase == "section_writing"
    assert state.active_artifact == "introduction_related_work.tex"
    assert "Method skeleton stays intact." in latex
    assert "\\section{Introduction}" in latex
    assert "\\section{Related Work}" in latex
    assert "smith2020" in latex and "lee2021" in latex
    assert state.artifacts.latest_validation_json is not None
    assert read_json(state.artifacts.latest_validation_json)["stage"] == "intro_related"
    assert any(note.startswith("Lane manifest recorded:") for note in state.notes)


def test_write_intro_related_repair_loop_blocks_strict_unknown_citation_then_recovers(tmp_path: Path) -> None:
    cwd = _seed_intro_related_session(tmp_path)
    provider = SequenceProvider(
        [
            _intro_related_latex("ghost2024"),
            _intro_related_latex("smith2020,lee2021"),
        ]
    )

    output_path = write_intro_related(
        cwd,
        provider,
        claim_safe=True,
        allow_recoverable_contract_issues=True,
    )

    latex = output_path.read_text(encoding="utf-8")
    notes = "\n".join(_lane_notes(cwd))
    assert len(provider.requests) == 2
    assert "ghost2024" not in latex
    assert "smith2020" in latex and "lee2021" in latex
    assert "repair attempt 1 ran after citation-contract validation failure" in notes
    assert "Blocked unsupported citation keys in strict Introduction/Related Work draft: ghost2024(2)" in notes
    assert read_json(load_session(cwd).artifacts.latest_validation_json)["ok"] is True


def test_write_intro_related_records_canonical_alias_replacements(tmp_path: Path) -> None:
    cwd = _seed_intro_related_session(
        tmp_path,
        citation_map={
            "smith2020": {"title": "Grounded Writing", "year": 2020, "abstract": "Evidence-grounded writing."},
            "aliasA": {"canonical_bibtex_key": "smith2020", "title": "Grounded Writing Alias"},
            "lee2021": {"title": "Agentic Review", "year": 2021, "abstract": "Agentic manuscript review."},
        },
    )
    provider = SequenceProvider([_intro_related_latex("aliasA,lee2021")])

    output_path = write_intro_related(cwd, provider, allow_recoverable_contract_issues=True)

    latex = output_path.read_text(encoding="utf-8")
    notes = "\n".join(_lane_notes(cwd))
    assert "\\cite{smith2020,lee2021}" in latex
    assert "aliasA" not in latex
    assert "Canonicalized citation-key aliases in Introduction/Related Work draft: aliasA->smith2020" in notes
    assert read_json(load_session(cwd).artifacts.latest_validation_json)["ok"] is True


def test_write_intro_related_bridges_small_citation_coverage_shortfall_after_repairs(tmp_path: Path) -> None:
    cwd = _seed_intro_related_session(tmp_path)
    provider = SequenceProvider(
        [
            _intro_related_latex("smith2020"),
            _intro_related_latex("smith2020"),
            _intro_related_latex("smith2020"),
        ]
    )

    output_path = write_intro_related(cwd, provider, allow_recoverable_contract_issues=True)

    latex = output_path.read_text(encoding="utf-8")
    notes = "\n".join(_lane_notes(cwd))
    assert len(provider.requests) == 3
    assert "smith2020" in latex and "lee2021" in latex
    assert "\\paragraph{Additional related context.}" in latex
    assert "Added a bounded related-work citation bridge" in notes
    assert read_json(load_session(cwd).artifacts.latest_validation_json)["ok"] is True
