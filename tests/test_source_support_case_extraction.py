from __future__ import annotations

import json
from pathlib import Path

from paperorchestra.core.models import ArtifactIndex, InputBundle, SessionState
from paperorchestra.core.session import save_session, set_current_session
from paperorchestra.reviews import source_support, source_support_cases


def test_build_source_backed_citation_cases_from_latex_tracks_sections_paragraphs_and_titles() -> None:
    latex = r"""
\documentclass{article}
\title{Hidden preamble cite \cite{ignored}}
\begin{document}
\section{Method}
Precision is 1.0 in the benchmark. Prior work differs~\cite{smith2024,doe2025}.

No citation here.

\section{Discussion}
A second claim cites one source \citep[see][p. 2]{smith2024}.
\end{document}
"""
    citation_map = {
        "smith2024": {"title": "Smith on SAST", "url": "https://example.org/smith"},
        "doe2025": {"title": "Doe on Triage", "doi": "10.1000/doe"},
    }

    cases = source_support_cases.build_source_backed_citation_cases_from_latex(latex, citation_map)

    assert [case["id"] for case in cases] == ["C1", "C2", "C3"]
    assert [case["key"] for case in cases] == ["smith2024", "doe2025", "smith2024"]
    assert cases[0]["loc"] == "Method ¶1"
    assert cases[2]["loc"] == "Discussion ¶2"
    assert cases[0]["anchor"] == r"Prior work differs~\cite{smith2024,doe2025}."
    assert cases[0]["target"] == "Prior work differs "
    assert cases[0]["source"]["title"] == "Smith on SAST"
    assert cases[1]["source"]["doi"] == "10.1000/doe"


def test_build_source_backed_citation_cases_session_path_uses_citation_review_body(tmp_path: Path) -> None:
    paper = tmp_path / "paper.full.tex"
    paper.write_text(
        r"""
\documentclass{article}
\begin{document}
\section{Intro}
A grounded claim cites a source \cite{smith2024}.
\end{document}
""",
        encoding="utf-8",
    )
    citation_map = tmp_path / "citation_map.json"
    citation_map.write_text(json.dumps({"smith2024": {"title": "Smith Source"}}), encoding="utf-8")
    state = SessionState(
        session_id="po-source-cases",
        created_at="2026-06-18T00:00:00+00:00",
        updated_at="2026-06-18T00:00:00+00:00",
        current_phase="test",
        active_artifact=None,
        inputs=InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experimental.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
        artifacts=ArtifactIndex(paper_full_tex=str(paper), citation_map_json=str(citation_map)),
    )
    save_session(tmp_path, state)
    set_current_session(tmp_path, state.session_id)

    cases = source_support.build_source_backed_citation_cases(tmp_path, resolve_evidence=False)

    assert len(cases) == 1
    assert cases[0]["loc"] == "Intro ¶1"
    assert cases[0]["target"] == "A grounded claim cites a source "
