import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def assert_mentions(skill: str, *tokens: str) -> None:
    text = skill_text(skill)
    missing = [token for token in tokens if token not in text]
    assert not missing, f"{skill} missing required tokens: {missing}"


def test_authoring_round_invokes_research_swarm_for_broad_multi_cluster_citation_gaps() -> None:
    assert_mentions(
        "paperorchestra-authoring-round",
        "$paperorchestra-research-swarm",
        "broad/multi-cluster citation/source",
        "Invoke `$paperorchestra-research-swarm`",
        "before drafting prose",
        "Required companions must be invoked before manuscript prose",
    )


def test_paperorchestra_skills_route_broad_source_gaps_to_research_swarm() -> None:
    for skill in [
        "paperorchestra",
        "paperorchestra-authoring-round",
        "paperorchestra-live-review",
        "paperorchestra-quality-gate",
        "paperorchestra-status",
        "paperorchestra-plan",
    ]:
        assert_mentions(
            skill,
            "$paperorchestra-research-swarm",
            "broad/multi-cluster",
            "citation/source",
        )
    intake = skill_text("paperorchestra-intake")
    assert "Invoke `$paperorchestra-research-swarm`" not in intake
    assert "Do not start `$paperorchestra-research-swarm`" in intake


def test_research_swarm_requires_parallel_omx_lanes_and_autoresearch_gate() -> None:
    assert_mentions(
        "paperorchestra-research-swarm",
        "OMX companion routing",
        "$ultrawork",
        "$team",
        "parallel subagent lanes",
        "$autoresearch",
        "validator",
        "completion artifact",
        "mission-validator-script",
        "prompt-architect-artifact",
        "agent_type=researcher",
        "agent_type=verifier",
        "`researcher` workers",
    )


def test_research_swarm_documents_required_lane_artifacts() -> None:
    assert_mentions(
        "paperorchestra-research-swarm",
        "research-swarm-plan.md",
        "lane-",
        "findings.md",
        "synthesis.md",
        "autoresearch-state.json",
        "result.json",
        "research-swarm.manifest.json",
        "prior_work_seed.json",
        "citation_map.json",
        "references.bib",
    )


def test_research_swarm_installs_with_paperorchestra_skills(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    subprocess.run(
        [str(ROOT / "scripts" / "install-skill.sh"), str(target)],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    installed_skill = target / "paperorchestra-research-swarm" / "SKILL.md"
    installed_agent = target / "paperorchestra-research-swarm" / "agents" / "openai.yaml"
    assert installed_skill.exists()
    assert installed_agent.exists()
    assert installed_skill.read_text(encoding="utf-8") == skill_text("paperorchestra-research-swarm")
    assert "$paperorchestra-research-swarm" in installed_agent.read_text(encoding="utf-8")
