from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
PAPERO_SKILLS = {
    path.parent.name
    for path in SKILLS.glob("paperorchestra*/SKILL.md")
}


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def assert_mentions(skill: str, *tokens: str) -> None:
    text = skill_text(skill)
    missing = [token for token in tokens if token not in text]
    assert not missing, f"{skill} is missing explicit routing tokens: {missing}"


def test_all_paperorchestra_skills_have_omx_guidance() -> None:
    assert PAPERO_SKILLS == {
        "paperorchestra",
        "paperorchestra-authoring-round",
        "paperorchestra-intake",
        "paperorchestra-figure",
        "paperorchestra-visual-audit",
        "paperorchestra-live-review",
        "paperorchestra-plan",
        "paperorchestra-quality-gate",
        "paperorchestra-setup",
        "paperorchestra-status",
    }
    for skill in PAPERO_SKILLS - {"paperorchestra-status"}:
        assert_mentions(skill, "OMX companion routing")
    assert_mentions("paperorchestra-status", "OMX companion hints")


def test_router_names_core_omx_companion_workflows() -> None:
    assert_mentions(
        "paperorchestra",
        "OMX companion routing",
        "$deep-interview",
        "$ralplan",
        "$ultrawork",
        "$ralph",
        "$autoresearch",
        "$best-practice-research",
        "$ultraqa",
    )


def test_authoring_round_routes_research_parallel_and_persistent_lanes() -> None:
    assert_mentions(
        "paperorchestra-authoring-round",
        "OMX companion routing",
        "$ultrawork",
        "$autoresearch",
        "$best-practice-research",
        "$ralph",
        "$ultraqa",
    )


def test_review_and_quality_gate_route_followup_workflows() -> None:
    assert_mentions(
        "paperorchestra-live-review",
        "OMX companion routing",
        "$autoresearch",
        "$best-practice-research",
        "$ralph",
        "$ultraqa",
    )
    assert_mentions(
        "paperorchestra-quality-gate",
        "OMX companion routing",
        "$autoresearch",
        "$best-practice-research",
        "$ralph",
        "$ultrawork",
        "$ultraqa",
    )
    assert_mentions(
        "paperorchestra-visual-audit",
        "OMX companion routing",
        "$visual-verdict",
        "$ultrawork",
        "$ralph",
        "$paperorchestra-quality-gate",
    )


def test_intake_plan_and_setup_route_to_narrow_omx_surfaces() -> None:
    assert_mentions(
        "paperorchestra-intake",
        "$deep-interview",
        "$paperorchestra-status",
        "$paperorchestra-plan",
    )
    assert_mentions(
        "paperorchestra-plan",
        "$ralplan",
        "$best-practice-research",
        "$autoresearch",
        "$ultrawork",
    )
    assert_mentions(
        "paperorchestra-setup",
        "$omx-setup",
        "$paperorchestra-status",
        "$paperorchestra-live-review",
        "$paperorchestra-quality-gate",
    )


def test_status_reports_next_paperorchestra_skill_and_omx_companion() -> None:
    assert_mentions(
        "paperorchestra-status",
        "OMX companion hints",
        "$paperorchestra-intake + $deep-interview",
        "$paperorchestra-plan + $ralplan",
        "$paperorchestra-authoring-round + $ultrawork",
        "$paperorchestra-authoring-round + $ralph",
        "$paperorchestra-live-review + $autoresearch",
        "$paperorchestra-live-review + $best-practice-research",
        "$paperorchestra-quality-gate + $ultraqa",
        "$paperorchestra-visual-audit + $visual-verdict",
    )
