from __future__ import annotations

import json
import html
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.core.session import review_path, set_current_session
from paperorchestra.engine import refine_context, refine_stages


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8")
    return str(path)


def _data_block_payload(prompt: str, name: str) -> dict:
    start = prompt.index(f'<DATA_BLOCK name="{name}">') + len(f'<DATA_BLOCK name="{name}">')
    end = prompt.index("</DATA_BLOCK>", start)
    return json.loads(html.unescape(prompt[start:end].strip()))


def test_refine_stages_facade_reexports_iteration_context_helpers() -> None:
    assert refine_stages.RefinementIterationContext is refine_context.RefinementIterationContext
    assert refine_stages.build_refinement_iteration_context is refine_context.build_refinement_iteration_context


def test_build_refinement_iteration_context_loads_prompt_inputs(tmp_path: Path) -> None:
    set_current_session(tmp_path, "ctx-test")
    worklog_path = review_path(tmp_path, "refinement_worklog.iter-02.json")
    worklog_path.write_text('{"previous": true}', encoding="utf-8")
    paper = _write(tmp_path / "paper.tex", "\\section{Intro}\nBody")
    review = _write(tmp_path / "review.json", json.dumps({"overall_score": 4.2, "axis_scores": {"clarity": 3.5}}))
    citation_map = _write(tmp_path / "citation-map.json", json.dumps({"Key": {"title": "Source"}}))
    plot_manifest = _write(
        tmp_path / "plot-manifest.json",
        json.dumps({"figures": [{"figure_id": f"fig{i}"} for i in range(10)]}),
    )
    plot_assets = _write(
        tmp_path / "plot-assets.json",
        json.dumps({"assets": [{"figure_id": f"fig{i}"} for i in range(10)]}),
    )
    outline = _write(tmp_path / "outline.json", json.dumps({"section_plan": [{"section_title": "Intro"}]}))
    idea = _write(tmp_path / "idea.md", "idea")
    exp = _write(tmp_path / "exp.md", "precision improves")
    template = _write(tmp_path / "template.tex", "template")
    guidelines = _write(tmp_path / "guidelines.md", "guidelines")
    state = SimpleNamespace(
        refinement_iteration=2,
        artifacts=SimpleNamespace(
            paper_full_tex=paper,
            latest_review_json=review,
            citation_map_json=citation_map,
            plot_manifest_json=plot_manifest,
            plot_assets_json=plot_assets,
            outline_json=outline,
        ),
        inputs=SimpleNamespace(
            idea_path=idea,
            experimental_log_path=exp,
            template_path=template,
            guidelines_path=guidelines,
            figures_dir=None,
        ),
    )

    context = refine_context.build_refinement_iteration_context(
        tmp_path,
        state,
        claim_safe=True,
        writer_brief={},
    )

    assert context.candidate_iter == 3
    assert context.current_paper == "\\section{Intro}\nBody"
    assert context.review_payload["overall_score"] == 4.2
    assert context.strict_claim_safe_prompt is True
    assert context.previous_worklog == '{"previous": true}'
    assert context.expected_section_titles == ["Intro"]
    assert len(context.prompt_plot_manifest["figures"]) == 8
    assert len(context.prompt_plot_assets_index["assets"]) == 8
    assert '<DATA_BLOCK name="reviewer_feedback">' in context.user_prompt
    reviewer_feedback = _data_block_payload(context.user_prompt, "reviewer_feedback")
    assert "overall_score" not in reviewer_feedback
    assert "axis_scores" not in reviewer_feedback
    assert reviewer_feedback["score_redaction"]["overall_score_removed"] == "writer_blind_to_reviewer_scores"
    assert "score_redaction" in context.user_prompt
    assert "4.2" not in context.user_prompt
    assert "3.5" not in context.user_prompt
    assert '<DATA_BLOCK name="worklog.json">' in context.user_prompt
