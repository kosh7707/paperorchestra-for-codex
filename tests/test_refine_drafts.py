from __future__ import annotations

import pytest

from paperorchestra.core.errors import ContractError
from paperorchestra.engine import refine_drafts


def test_parse_refinement_response_synthesizes_worklog_when_json_missing() -> None:
    response = r"""
```latex
\documentclass{article}
\begin{document}
Body
\end{document}
```
"""

    worklog, latex, notes = refine_drafts.parse_refinement_response(response, lane_notes=["seed"])

    assert worklog["addressed_weaknesses"] == []
    assert "machine-readable worklog" in worklog["actions_taken"][0]
    assert latex.startswith(r"\documentclass")
    assert notes[0] == "seed"
    assert "omitted JSON worklog" in notes[-1]


def test_parse_refinement_response_uses_machine_readable_worklog() -> None:
    response = r"""
```json
{"actions_taken": ["tightened intro"], "addressed_weaknesses": ["framing"]}
```

```latex
\documentclass{article}
\begin{document}
Refined
\end{document}
```
"""

    worklog, latex, notes = refine_drafts.parse_refinement_response(response, lane_notes=["seed"])

    assert worklog["actions_taken"] == ["tightened intro"]
    assert worklog["addressed_weaknesses"] == ["framing"]
    assert latex.startswith(r"\documentclass")
    assert notes == ["seed"]


def test_parse_refinement_response_raises_contract_error_without_latex() -> None:
    with pytest.raises(ContractError, match="extractable LaTeX"):
        refine_drafts.parse_refinement_response("", lane_notes=[])


def test_normalize_refinement_latex_runs_postprocessors_in_order(monkeypatch) -> None:
    calls: list[str] = []

    def step(name):
        def _inner(latex, *args):
            calls.append(name)
            return latex + f"|{name}"

        return _inner

    monkeypatch.setattr(refine_drafts, "_ensure_bibliography_hook", step("bibliography"))
    monkeypatch.setattr(refine_drafts, "_normalize_generated_plot_paths", step("generated_paths"))
    monkeypatch.setattr(refine_drafts, "_normalize_source_figure_paths", step("source_paths"))
    monkeypatch.setattr(refine_drafts, "_ensure_generated_plot_usage", step("generated_usage"))
    monkeypatch.setattr(refine_drafts, "_stabilize_figure_float_placement", step("float_placement"))
    monkeypatch.setattr(refine_drafts, "_remove_material_packet_sections", step("remove_packets"))
    monkeypatch.setattr(refine_drafts, "_ensure_discussion_section_for_claim_boundaries", step("discussion"))
    monkeypatch.setattr(refine_drafts, "_ensure_required_claim_scope_notes", step("scope_notes"))

    def canonicalize(latex, citation_map):
        calls.append("canonicalize")
        return latex + "|canonicalize", {"Alias": "Real"}

    monkeypatch.setattr(refine_drafts, "canonicalize_citation_keys", canonicalize)

    latex, replacements = refine_drafts.normalize_refinement_latex(
        "draft",
        citation_map={"Real": {}},
        plot_assets_index={"assets": []},
        figures_dir="figures",
        claim_map={"claims": []},
    )

    assert calls == [
        "bibliography",
        "generated_paths",
        "source_paths",
        "generated_usage",
        "float_placement",
        "remove_packets",
        "discussion",
        "scope_notes",
        "canonicalize",
    ]
    assert latex == "draft|bibliography|generated_paths|source_paths|generated_usage|float_placement|remove_packets|discussion|scope_notes|canonicalize"
    assert replacements == {"Alias": "Real"}
