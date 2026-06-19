from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.io import write_json
from paperorchestra.core.models import InputBundle, SessionState
from paperorchestra.core.session import artifact_path, create_session, save_session
from paperorchestra.manuscript.narrative_payloads import build_planning_payloads


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def _seed_session(
    tmp_path: Path,
    *,
    outline: dict[str, object],
    citation_map: dict[str, object] | None = None,
    idea_text: str = "The method is an evidence-grounded pipeline. A limitation is that humans finalize claims.",
    experimental_text: str = "Evaluation results report a 1.0 recall operating point and benchmark measurements.",
    template_text: str | None = None,
) -> SessionState:
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=_write(
                tmp_path / "idea.md",
                idea_text,
            ),
            experimental_log_path=_write(
                tmp_path / "experimental.md",
                experimental_text,
            ),
            template_path=_write(
                tmp_path / "template.tex",
                template_text
                or r"""\documentclass{article}
\begin{document}
\section{Introduction}
\section{Method}
\section{Experiments}
\end{document}
""",
            ),
            guidelines_path=_write(tmp_path / "guidelines.md", "Use LNCS style."),
        ),
    )
    outline_path = artifact_path(tmp_path, "outline.json")
    citation_path = artifact_path(tmp_path, "citation_map.json")
    write_json(outline_path, outline)
    write_json(citation_path, citation_map or {})
    state.artifacts.outline_json = str(outline_path)
    state.artifacts.citation_map_json = str(citation_path)
    save_session(tmp_path, state)
    return state


def test_planning_payload_adds_discussion_when_outline_contains_material_control_section(tmp_path: Path) -> None:
    _seed_session(
        tmp_path,
        outline={
            "section_plan": [
                {"section_title": "Introduction"},
                {"section_title": "Claim Boundaries for Test Draft"},
                {"section_title": "Method"},
            ]
        },
    )

    narrative, claim_map, _citation_plan = build_planning_payloads(tmp_path)

    section_titles = [role["section_title"] for role in narrative["section_roles"]]
    assert "Claim Boundaries for Test Draft" not in section_titles
    assert "Discussion" in section_titles
    limitation_claims = [claim for claim in claim_map["claims"] if claim["claim_type"] == "limitation"]
    assert limitation_claims
    assert limitation_claims[0]["target_section"] == "Discussion"


def test_planning_payload_keeps_positioning_claim_when_outline_has_minimal_sections(tmp_path: Path) -> None:
    _seed_session(
        tmp_path,
        outline={"section_plan": [{"section_title": "Method"}]},
        citation_map={"smith2024": {"title": "Grounded Paper Writing", "provenance": {"secret": True}}},
    )

    narrative, claim_map, citation_plan = build_planning_payloads(tmp_path)

    positioning = [claim for claim in claim_map["claims"] if claim["claim_type"] == "positioning"]
    assert len(positioning) == 1
    assert positioning[0]["target_section"] == "Method"
    assert positioning[0]["citation_keys"] == []
    citation_excerpt = positioning[0]["evidence_anchors"][0]["evidence_excerpt"]
    assert "provenance" not in json.loads(citation_excerpt)
    assert citation_plan["placements"] == []
    assert any(beat["target_section"] == "Method" for beat in narrative["story_beats"])


def test_planning_payload_uses_template_sections_when_outline_is_empty(tmp_path: Path) -> None:
    _seed_session(
        tmp_path,
        outline={"section_plan": []},
        template_text=r"""\documentclass{article}
\begin{document}
\section{Introduction}
\section*{Related Work}
\section{Custom Method}
\end{document}
""",
    )

    narrative, _claim_map, _citation_plan = build_planning_payloads(tmp_path)

    assert [role["section_title"] for role in narrative["section_roles"]] == [
        "Introduction",
        "Related Work",
        "Custom Method",
    ]


def test_template_latex_commands_do_not_create_method_claim_from_boilerplate(tmp_path: Path) -> None:
    _seed_session(
        tmp_path,
        outline={"section_plan": []},
        idea_text="A concise positioning note with no technical seed.",
        experimental_text="Qualitative notes only.",
        template_text=r"""\documentclass{article}
\method{x}
\algorithm{x}
\pipeline{x}
\architecture{x}
\framework{x}
\implementation{x}
\construction{x}
\design{x}
\system{x}
\model{x}
\approach{x}
\begin{document}
\section{Background}
Plain template boilerplate contains enough ordinary words to exceed the term threshold without technical seeds.
\end{document}
""",
    )

    _narrative, claim_map, _citation_plan = build_planning_payloads(tmp_path)

    assert [claim["claim_type"] for claim in claim_map["claims"]] == []


def test_planning_payload_targets_system_results_and_related_work_sections(tmp_path: Path) -> None:
    _seed_session(
        tmp_path,
        outline={
            "section_plan": [
                {"section_title": "Introduction"},
                {"section_title": "System"},
                {"section_title": "Experiment Setup"},
                {"section_title": "Results"},
                {"section_title": "Related Work"},
                {"section_title": "Conclusion"},
            ]
        },
        citation_map={"smith2024": {"title": "Grounded Paper Writing"}},
    )

    narrative, claim_map, citation_plan = build_planning_payloads(tmp_path)

    method_claims = [claim for claim in claim_map["claims"] if claim["claim_type"] == "method"]
    benchmark_claims = [claim for claim in claim_map["claims"] if claim["claim_type"] == "benchmark"]
    positioning_claims = [claim for claim in claim_map["claims"] if claim["claim_type"] == "positioning"]
    assert method_claims and method_claims[0]["target_section"] == "System"
    assert benchmark_claims and benchmark_claims[0]["target_section"] == "Results"
    assert positioning_claims and positioning_claims[0]["target_section"] == "Related Work"
    role_titles = [role["section_title"] for role in narrative["section_roles"]]
    assert role_titles == ["Introduction", "System", "Experiment Setup", "Results", "Related Work", "Conclusion"]
    assert citation_plan["placements"] == []
