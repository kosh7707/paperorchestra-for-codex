import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
FIGURE_SKILL = SKILLS / "paperorchestra-figure" / "SKILL.md"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def skill_text(name: str) -> str:
    return text(SKILLS / name / "SKILL.md")


def assert_contains(label: str, haystack: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in haystack]
    assert not missing, f"{label} is missing: {missing}"


def test_paperorchestra_figure_skill_exists_with_figure_contract() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Figure intent contract",
        "rhetorical job",
        "supported claim",
        "source evidence",
        "caption contract",
        "placement contract",
    )


def test_figure_skill_handles_column_layout_and_latex_environment() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "one-column",
        "two-column",
        "figure*",
        "figure",
        "column width",
        "page width",
    )


def test_figure_skill_prefers_reproducible_vector_outputs_and_gates_imagegen() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Mermaid",
        "SVG",
        "TikZ",
        "vector-first",
        "imagegen",
        "bitmap illustration",
    )


def test_figure_skill_rejects_imagegen_for_precise_diagrams() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Do not use imagegen for diagrams that must preserve exact node labels, arrows, numeric results, code paths, or reproducible layout.",
    )


def test_figure_skill_requires_caption_evidence_map() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Caption evidence map",
        "caption sentence",
        "supported claim",
        "source artifact/data/code/citation",
        "caveat/boundary",
        "downgrade or reject",
    )


def test_figure_skill_requires_template_inspection_before_figure_star() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "inspect the target template/guidelines",
        "figure* is for two-column templates only",
        "float differently",
        "compile or quality-gate verification",
        "figure-placement-review.json",
    )


def test_figure_skill_offers_remove_or_table_instead_of_generate() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "remove the figure",
        "convert to prose",
        "convert to table",
        "defer to human final artwork",
    )


def test_status_and_quality_gate_name_existing_figure_artifacts() -> None:
    for skill in ["paperorchestra-status", "paperorchestra-quality-gate"]:
        assert_contains(
            skill,
            skill_text(skill),
            "plot_manifest.json",
            "plot_assets.json",
            "plot_captions.json",
            "figure-placement-review.json",
            "figure_gate.report.json",
        )


def test_plan_shape_requires_full_figure_contract() -> None:
    assert_contains(
        "paperorchestra-plan",
        skill_text("paperorchestra-plan"),
        "caption contract",
        "placement contract",
        "output form",
        "TODO/final-artwork status",
    )


def test_live_review_routes_decorative_or_unsupported_figures_to_figure_skill() -> None:
    assert_contains(
        "paperorchestra-live-review",
        skill_text("paperorchestra-live-review"),
        "decorative",
        "unsupported",
        "unreadable",
        "weak-caption",
        "mispositioned",
        "$paperorchestra-figure",
    )


def test_figure_skill_fails_closed_on_claimed_bitmap_generation() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "If bitmap output is claimed",
        "must actually call the imagegen skill/tool",
        "report the generated artifact",
        "prompt only / no image generated",
    )


def test_figure_skill_requires_artifact_availability_checklist() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Artifact availability checklist",
        "present / missing / stale / not applicable",
        "figure-bearing manuscript",
        "block and route to `$paperorchestra-figure`",
    )


def test_figure_skill_forbids_final_figure_star_without_confirmed_two_column() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Do not emit a final LaTeX snippet that uses `figure*` unless two-column mode is confirmed",
        "unknown template",
        "use `figure` or mark the environment TODO",
    )


def test_figure_skill_final_card_contains_caption_safety_fields() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Caption evidence map:",
        "Self-contained/floating-caption check:",
        "Weak-caption status:",
        "weak caption rejected/downgraded",
    )


def test_figure_skill_preserves_paperorchestra_state_ownership() -> None:
    body = text(FIGURE_SKILL)
    assert_contains(
        "paperorchestra-figure",
        body,
        "Start with current PaperOrchestra session/status inspection",
        "unless purely reviewing a provided snippet",
        "route back to the owning workflow",
        "$paperorchestra-plan",
        "$paperorchestra-authoring-round",
        "$paperorchestra-quality-gate",
        "$paperorchestra-live-review",
    )


def test_status_and_quality_gate_block_missing_figure_artifacts() -> None:
    for skill in ["paperorchestra-status", "paperorchestra-quality-gate"]:
        assert_contains(
            skill,
            skill_text(skill),
            "present / missing / stale / not applicable",
            "figure-bearing manuscript",
            "$paperorchestra-figure",
        )


def test_workflow_routes_cover_full_figure_taxonomy() -> None:
    for skill in ["paperorchestra", "paperorchestra-plan", "paperorchestra-authoring-round"]:
        assert_contains(
            skill,
            skill_text(skill),
            "pipeline",
            "architecture",
            "taxonomy",
            "teaser",
            "result-summary",
            "case-study",
            "threat-model",
            "visual-abstract",
            "$paperorchestra-figure",
        )


def test_status_has_first_class_figure_repair_recommendation() -> None:
    assert_contains(
        "paperorchestra-status",
        skill_text("paperorchestra-status"),
        "figure-repair recommended",
        "figure-bearing manuscript",
        "figure assets, captions, supported claims, placement",
        "$paperorchestra-figure",
    )


def test_paperorchestra_workflow_skills_route_to_figure_skill() -> None:
    expected = {
        "paperorchestra": ["$paperorchestra-figure", "pipeline, architecture, taxonomy, teaser, result-summary, case-study, threat-model, or visual-abstract figures"],
        "paperorchestra-plan": ["$paperorchestra-figure", "figure rhetorical job", "placement"],
        "paperorchestra-authoring-round": ["$paperorchestra-figure", "figure-dependent section"],
        "paperorchestra-live-review": ["$paperorchestra-figure", "figure is decorative"],
        "paperorchestra-quality-gate": ["$paperorchestra-figure", "figure-caption alignment", "figure placement"],
        "paperorchestra-status": ["$paperorchestra-figure", "figure assets"],
    }
    for skill, needles in expected.items():
        assert_contains(skill, skill_text(skill), *needles)


def test_figure_skill_installs_with_other_paperorchestra_skills(tmp_path: Path) -> None:
    target = tmp_path / "skills"
    subprocess.run(
        [str(ROOT / "scripts" / "install-skill.sh"), str(target)],
        check=True,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    installed = target / "paperorchestra-figure" / "SKILL.md"
    assert installed.exists()
    assert text(installed) == text(FIGURE_SKILL)
