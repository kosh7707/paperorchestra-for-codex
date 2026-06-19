from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import read_json, write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, save_session
from paperorchestra.engine import outline_stage
from paperorchestra.engine.plan_gate import approved_plan_path
from paperorchestra.manuscript.narrative_artifacts import write_planning_artifacts, planning_artifact_status
from paperorchestra.manuscript.narrative_context import load_planning_context
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class _Provider(BaseProvider):
    name = "capture"

    def complete(self, request: CompletionRequest) -> str:
        raise AssertionError("outline_stage completion should be monkeypatched")


def _seed_session(tmp_path: Path):
    (tmp_path / "idea.md").write_text("Original idea without final section naming.", encoding="utf-8")
    (tmp_path / "experimental.md").write_text("Experiment notes.", encoding="utf-8")
    (tmp_path / "template.tex").write_text("\\documentclass{article}\n\\begin{document}\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "guidelines.md").write_text("IEEE style.", encoding="utf-8")
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=str(tmp_path / "idea.md"),
            experimental_log_path=str(tmp_path / "experimental.md"),
            template_path=str(tmp_path / "template.tex"),
            guidelines_path=str(tmp_path / "guidelines.md"),
        ),
    )
    return state


def test_approved_plan_path_ignores_unapproved_plans(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text("# Plan\n\nNot yet approved.", encoding="utf-8")

    assert approved_plan_path(tmp_path) is None

    (tmp_path / "paper-plan.md").write_text(
        "# Plan\n\n<!-- paperorchestra:plan-approved -->\n", encoding="utf-8"
    )

    assert approved_plan_path(tmp_path) == tmp_path / "paper-plan.md"


def test_outline_prompt_includes_author_approved_plan(tmp_path: Path, monkeypatch) -> None:
    _seed_session(tmp_path)
    (tmp_path / "paper-plan.md").write_text(
        "# Paper Plan\n\n<!-- paperorchestra:plan-approved -->\n\nUse Methodology, Experiment Setup, Results, and Related Work.",
        encoding="utf-8",
    )
    captured = {}

    def complete(request, **kwargs):
        captured["user_prompt"] = request.user_prompt
        return (
            '{"section_plan":[{"section_title":"Methodology"},'
            '{"section_title":"Experiment Setup"},{"section_title":"Results"}],'
            '"plotting_plan":[],"intro_related_work_plan":[],"key_claims":[]}'
        ), "ralph", False, []

    monkeypatch.setattr(outline_stage, "_complete_with_runtime_mode", complete)
    monkeypatch.setattr(outline_stage, "record_lane_manifest", lambda *args, **kwargs: tmp_path / "lane.json")

    outline_stage.generate_outline(tmp_path, _Provider())

    assert "paper-plan.md" in captured["user_prompt"]
    assert "Use Methodology, Experiment Setup, Results, and Related Work." in captured["user_prompt"]


def test_planning_context_and_freshness_include_approved_plan(tmp_path: Path) -> None:
    state = _seed_session(tmp_path)
    (tmp_path / "paper-plan.md").write_text(
        "# Paper Plan\n\n<!-- paperorchestra:plan-approved -->\n\nApproved section contract mentions Results.",
        encoding="utf-8",
    )
    outline_path = artifact_path(tmp_path, "outline.json")
    citation_path = artifact_path(tmp_path, "citation_map.json")
    write_json(outline_path, {"section_plan": [{"section_title": "Results"}]})
    write_json(citation_path, {})
    state.artifacts.outline_json = str(outline_path)
    state.artifacts.citation_map_json = str(citation_path)
    save_session(tmp_path, state)

    context = load_planning_context(tmp_path)
    assert "Approved section contract mentions Results" in context.planning_text

    write_planning_artifacts(tmp_path)
    assert planning_artifact_status(tmp_path)["status"] == "pass"

    (tmp_path / "paper-plan.md").write_text(
        "# Paper Plan\n\n<!-- paperorchestra:plan-approved -->\n\nApproved section contract changed to Discussion.",
        encoding="utf-8",
    )

    status = planning_artifact_status(tmp_path)
    assert status["status"] == "fail"
    assert "narrative_plan_stale" in status["failing_codes"]
