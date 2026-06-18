from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from paperorchestra.loop_engine.quality.utils import _file_sha256
from paperorchestra.loop_engine.quality.action_families import figures


def _state(*, review_path: Path | None = None, paper_path: Path | None = None, assets_path: Path | None = None):
    return SimpleNamespace(
        artifacts=SimpleNamespace(
            latest_figure_placement_review_json=str(review_path) if review_path else None,
            paper_full_tex=str(paper_path) if paper_path else None,
            plot_assets_json=str(assets_path) if assets_path else None,
        )
    )


def test_figure_review_actions_emit_human_needed_context_for_failures(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("body", encoding="utf-8")
    review = tmp_path / "figure-review.json"
    review.write_text(
        json.dumps(
            {
                "manuscript_sha256": _file_sha256(paper),
                "figures": [
                    {
                        "label": "fig:flow",
                        "section_title": "Method",
                        "failing_codes": ["missing_technical_grounding"],
                        "warning_codes": ["tail_clump"],
                        "included_assets": ["flow.pdf"],
                        "plot_manifest_match": {"purpose": "Pipeline overview"},
                        "nearby_reference_context": "Figure appears after the discussion.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    produced = figures._figure_review_actions(_state(review_path=review, paper_path=paper))

    assert [action["code"] for action in produced] == ["missing_technical_grounding", "tail_clump"]
    assert all(action["automation"] == "human_needed" for action in produced)
    assert all(action["approval_required_from"] == "figure_placement_review_critic" for action in produced)
    assert "Pipeline overview" in produced[0]["reason"]
    assert produced[0]["source"] == str(review)


def test_figure_review_actions_ignore_stale_review(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("current body", encoding="utf-8")
    review = tmp_path / "figure-review.json"
    review.write_text(
        json.dumps({"manuscript_sha256": "old", "figures": [{"label": "fig", "failing_codes": ["x"]}]}),
        encoding="utf-8",
    )

    assert figures._figure_review_actions(_state(review_path=review, paper_path=paper)) == []


def test_generated_placeholder_figure_actions_require_placeholder_usage(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text("Uses generated/fig-placeholder.tex here.", encoding="utf-8")
    assets = tmp_path / "plot-assets.json"
    assets.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "figure_id": "placeholder-1",
                        "asset_kind": "generated_placeholder",
                        "latex_snippet_path": "generated/fig-placeholder.tex",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    produced = figures._generated_placeholder_figure_actions(_state(paper_path=paper, assets_path=assets))

    assert len(produced) == 1
    assert produced[0]["code"] == "final_figure_assets_non_reviewable"
    assert produced[0]["target"] == "final figures"
    assert produced[0]["source"] == str(assets)
