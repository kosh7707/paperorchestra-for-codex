import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
ACADEMIC_REF = SKILLS / "paperorchestra" / "references" / "academic-writing.md"
CORE_WRITING_SKILLS = [
    "paperorchestra",
    "paperorchestra-intake",
    "paperorchestra-plan",
    "paperorchestra-authoring-round",
    "paperorchestra-live-review",
    "paperorchestra-quality-gate",
]


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def skill_text(name: str) -> str:
    return text(SKILLS / name / "SKILL.md")


def assert_contains(label: str, haystack: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in haystack]
    assert not missing, f"{label} is missing: {missing}"


def test_academic_writing_reference_defines_general_paper_contract() -> None:
    body = text(ACADEMIC_REF)
    assert_contains(
        "academic-writing.md",
        body,
        "Phenomenon → Gap → Contribution → Evidence → Boundary → Implication",
        "Sentence Intent Principle",
        "systems paper",
        "methodology or benchmark paper",
        "empirical paper",
        "survey or review paper",
        "position paper",
    )


def test_core_paper_skills_load_academic_writing_reference() -> None:
    for skill in CORE_WRITING_SKILLS:
        assert_contains(
            skill,
            skill_text(skill),
            "references/academic-writing.md",
            "Phenomenon → Gap → Contribution → Evidence → Boundary → Implication",
        )


def test_planning_authoring_and_review_operationalize_sentence_intent() -> None:
    assert_contains(
        "paperorchestra-plan",
        skill_text("paperorchestra-plan"),
        "rhetorical job",
        "reader belief before",
        "reader belief after",
    )
    assert_contains(
        "paperorchestra-authoring-round",
        skill_text("paperorchestra-authoring-round"),
        "Sentence Intent Principle",
        "paragraph-level rhetorical job",
        "claim-evidence-boundary",
    )
    assert_contains(
        "paperorchestra-live-review",
        skill_text("paperorchestra-live-review"),
        "paper-likeness",
        "sentence intent",
        "Related Work",
    )
    assert_contains(
        "paperorchestra-quality-gate",
        skill_text("paperorchestra-quality-gate"),
        "sentence-intent alignment",
        "claim-evidence-boundary alignment",
        "narrative coherence",
    )


def test_install_skill_copies_reference_resources(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    stale = target / "paperorchestra-plan" / "references" / "stale.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("obsolete", encoding="utf-8")

    subprocess.run(
        [str(ROOT / "scripts" / "install-skill.sh"), str(target)],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    installed = target / "paperorchestra" / "references" / "academic-writing.md"
    assert installed.exists()
    assert text(installed) == text(ACADEMIC_REF)
    assert not stale.exists()
