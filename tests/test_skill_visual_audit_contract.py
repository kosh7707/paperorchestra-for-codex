from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "paperorchestra-visual-audit" / "SKILL.md"


def test_visual_audit_skill_routes_to_vision_and_repair_loop() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "OMX companion routing" in text
    assert "$visual-verdict" in text
    assert "$ralph" in text
    assert "paperorchestra visual-audit" in text
    assert "scripts/check-cli-surface.py" in text
    assert "PYTHONPATH=/path/to/paperorchestra-for-codex python3 -m paperorchestra.cli visual-audit --help" in text
    assert "visual_repair_brief.json" in text
    assert "visual_repair_candidate.json" in text
    assert "claim" in text.lower()
    assert "caption" in text.lower()
    assert "one-column" in text or "two-column" in text


def test_visual_audit_skill_names_ai_artifact_findings_for_figures() -> None:
    text = SKILL.read_text(encoding="utf-8")

    assert "AI-generated-artifact tells" in text
    assert "ai_generated_artifact" in text
    assert "--require-ai-artifact-check" in text
    assert "--require-publication-figure-check" in text
    assert "publication-readiness" in text
