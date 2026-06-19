from __future__ import annotations

from pathlib import Path

from paperorchestra.core.io import write_json
from paperorchestra.core.models import InputBundle
from paperorchestra.core.session import artifact_path, create_session, load_session, save_session
from paperorchestra.engine import authoring_round
from paperorchestra.runtime.provider_base import BaseProvider, CompletionRequest


class _NoCallProvider(BaseProvider):
    name = "no-call"

    def complete(self, request: CompletionRequest) -> str:  # pragma: no cover - patched workflow should not call it directly
        raise AssertionError("provider should be consumed only by patched authoring-round steps")


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def _install_planning_patches(tmp_path: Path, monkeypatch, calls: list[str] | None = None) -> None:
    def generate_outline(cwd, provider, **kwargs):
        if calls is not None:
            calls.append("outline")
        path = artifact_path(cwd, "outline.json")
        write_json(
            path,
            {
                "plotting_plan": [],
                "intro_related_work_plan": {
                    "introduction_strategy": {"hook_hypothesis": "h", "problem_gap_hypothesis": "g", "search_directions": []},
                    "related_work_strategy": {"overview": "o", "subsections": []},
                },
                "section_plan": [{"section_title": "Introduction", "subsections": []}],
            },
        )
        state = load_session(cwd)
        state.artifacts.outline_json = str(path)
        save_session(cwd, state)
        return path

    def plan_narrative_and_claims(cwd, provider, **kwargs):
        if calls is not None:
            calls.append("narrative-plan")
        paths = {
            "narrative_plan": artifact_path(cwd, "narrative_plan.json"),
            "claim_map": artifact_path(cwd, "claim_map.json"),
            "citation_placement_plan": artifact_path(cwd, "citation_placement_plan.json"),
        }
        for name, path in paths.items():
            write_json(path, {"schema_version": name, "source_hashes": {}})
        state = load_session(cwd)
        state.artifacts.narrative_plan_json = str(paths["narrative_plan"])
        state.artifacts.claim_map_json = str(paths["claim_map"])
        state.artifacts.citation_placement_plan_json = str(paths["citation_placement_plan"])
        save_session(cwd, state)
        return paths

    monkeypatch.setattr(authoring_round, "generate_outline", generate_outline)
    monkeypatch.setattr(authoring_round, "plan_narrative_and_claims", plan_narrative_and_claims)


def _session(tmp_path: Path) -> None:
    (tmp_path / "paper-plan.md").write_text(
        "<!-- paperorchestra:plan-approved -->\n"
        "# Plan\n\n"
        "Thesis: evidence-grounded SAST alert triage should preserve recall while reducing false positives.\n",
        encoding="utf-8",
    )
    state = create_session(
        tmp_path,
        InputBundle(
            idea_path=_write(tmp_path / "idea.md", "Paper idea: SAST alert triage agent pipeline."),
            experimental_log_path=_write(tmp_path / "experiment.md", "Experiment basis: OWASP full run, numbers pending."),
            template_path=_write(tmp_path / "template.tex", "\\documentclass{article}\\begin{document}\\end{document}"),
            guidelines_path=_write(tmp_path / "guide.md", "Use an academic systems-paper structure."),
        ),
    )
    citation_map = tmp_path / ".paper-orchestra" / "runs" / state.session_id / "artifacts" / "citation_map.json"
    write_json(citation_map, {"iris2024": {"title": "IRIS", "authors": ["A"], "year": 2024}})
    state.artifacts.citation_map_json = str(citation_map)
    save_session(tmp_path, state)


def test_authoring_round_runs_literature_then_draft_then_critics(tmp_path: Path, monkeypatch) -> None:
    _session(tmp_path)
    calls: list[str] = []
    _install_planning_patches(tmp_path, monkeypatch, calls)

    def research_prior_work(cwd, provider, **kwargs):
        calls.append("literature")
        output = Path(kwargs["output"])
        write_json(output, {"references": [{"title": "Sifting the Noise", "year": 2023}]})
        return {"path": str(output), "reference_count": 1, "imported": {"status": "ok"}}

    def write_sections(cwd, provider, **kwargs):
        calls.append("draft")
        path = Path(kwargs["output_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\\documentclass{article}\n\\begin{document}\n\\section{Introduction}Draft \\cite{iris2024}.\n\\end{document}\n",
            encoding="utf-8",
        )
        state = load_session(cwd)
        state.artifacts.paper_full_tex = str(path)
        save_session(cwd, state)
        return path

    def review_current_paper(cwd, provider, **kwargs):
        calls.append("review")
        path = tmp_path / ".paper-orchestra" / "review.json"
        write_json(path, {"overall_score": 55, "major_issues": ["needs positioning"], "minor_issues": []})
        state = load_session(cwd)
        state.artifacts.latest_review_json = str(path)
        save_session(cwd, state)
        return path

    def write_section_review(cwd, output_path=None):
        calls.append("section-review")
        path = Path(output_path)
        write_json(path, {"overall_section_score": 70, "sections": []})
        return path

    def write_citation_support_review(cwd, output_path=None, **kwargs):
        calls.append("citation-review")
        path = Path(output_path)
        write_json(path, {"status": "heuristic", "findings": []})
        return path

    def write_revision_suggestions(source_paper, review_json, output_path, **kwargs):
        calls.append("revision-suggestions")
        path = Path(output_path)
        write_json(path, {"action_count": 1, "actions": []})
        return path

    monkeypatch.setattr(authoring_round, "research_prior_work", research_prior_work)
    monkeypatch.setattr(authoring_round, "write_sections", write_sections)
    monkeypatch.setattr(authoring_round, "review_current_paper", review_current_paper)
    monkeypatch.setattr(authoring_round, "write_section_review", write_section_review)
    monkeypatch.setattr(authoring_round, "write_citation_support_review", write_citation_support_review)
    monkeypatch.setattr(authoring_round, "write_revision_suggestions", write_revision_suggestions)
    monkeypatch.setattr(authoring_round, "get_citation_support_provider", lambda *args, **kwargs: None)

    result = authoring_round.run_authoring_round(
        tmp_path,
        _NoCallProvider(),
        citation_evidence_mode="heuristic",
        provider_name="mock",
    )

    assert calls == ["outline", "literature", "narrative-plan", "draft", "review", "section-review", "citation-review", "revision-suggestions"]
    assert result["status"] == "completed_with_critic"
    assert result["mode"] == "first_draft"
    assert Path(result["artifacts"]["positioning_brief"]["path"]).exists()
    assert Path(result["artifacts"]["manifest"]["path"]).exists()
    assert Path(result["artifacts"]["paper_full_tex"]["path"]).read_text(encoding="utf-8").startswith("\\documentclass")


def test_authoring_round_can_stop_after_draft_when_critic_disabled(tmp_path: Path, monkeypatch) -> None:
    _session(tmp_path)
    _install_planning_patches(tmp_path, monkeypatch)

    monkeypatch.setattr(authoring_round, "research_prior_work", lambda *args, **kwargs: {"path": kwargs["output"], "reference_count": 0})

    def write_sections(cwd, provider, **kwargs):
        path = Path(kwargs["output_path"])
        path.write_text("\\documentclass{article}\n\\begin{document}Draft.\\end{document}\n", encoding="utf-8")
        state = load_session(cwd)
        state.artifacts.paper_full_tex = str(path)
        save_session(cwd, state)
        return path

    monkeypatch.setattr(authoring_round, "write_sections", write_sections)

    result = authoring_round.run_authoring_round(
        tmp_path,
        _NoCallProvider(),
        run_critic=False,
        citation_evidence_mode="heuristic",
    )

    assert result["status"] == "drafted_without_critic"
    assert "review" not in result["artifacts"]
