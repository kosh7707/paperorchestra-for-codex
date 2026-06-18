from __future__ import annotations

from paperorchestra.engine import refine_prompt


def test_build_refinement_user_prompt_orders_context_blocks_and_redacts_scores() -> None:
    prompt = refine_prompt.build_refinement_user_prompt(
        paper_text="paper body",
        review_payload={"overall_score": 4.2, "axis_scores": {"clarity": 3.5}, "issues": [{"message": "tighten"}]},
        writer_brief={"sections": [{"title": "Intro"}]},
        experimental_log_text="precision improves",
        source_critical_context={"sources": ["official"]},
        citation_map={"Key": {"title": "A"}},
        plot_manifest={"figures": [{"figure_id": "fig1"}]},
        plot_assets_index={"assets": [{"figure_id": "fig1"}]},
        previous_worklog="{}",
    )

    labels = [
        "paper.tex",
        "reviewer_feedback",
        "scholarly_authoring_brief",
        "experimental_log.md",
        "source_critical_context.json",
        "citation_map.json",
        "plot_manifest.json",
        "plot_assets.json",
        "worklog.json",
    ]
    positions = [prompt.index(f'<DATA_BLOCK name="{label}">') for label in labels]

    assert positions == sorted(positions)
    assert "4.2" not in prompt
    assert "3.5" not in prompt
    assert "score_redaction" in prompt
    assert "Intro" in prompt
    assert prompt.endswith("</DATA_BLOCK>")
