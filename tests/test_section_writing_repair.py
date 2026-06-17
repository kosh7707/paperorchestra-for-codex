from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.engine import section_writing_repair as repair
from paperorchestra.runtime.providers import CompletionRequest


@dataclass(frozen=True)
class _Issue:
    code: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code}


class _Provider:
    name = "test-provider"


def test_repairable_section_issue_retries_and_records_retry_notes(monkeypatch) -> None:
    original_issue = _Issue("expected_section_too_shallow")
    calls: dict[str, Any] = {}

    def fake_complete(request: CompletionRequest, **kwargs: Any) -> tuple[str, str, bool, list[str]]:
        calls["request"] = request
        calls["kwargs"] = kwargs
        return "retry response", "retry_lane", True, ["retry note"]

    monkeypatch.setattr(repair, "_complete_with_runtime_mode", fake_complete)
    monkeypatch.setattr(repair, "extract_latex", lambda response: "retry latex")
    monkeypatch.setattr(
        repair,
        "normalize_section_draft",
        lambda latex, context: ("normalized retry", {"badkey": "goodkey"}, {"ghost": 1}),
    )
    monkeypatch.setattr(repair, "validate_section_draft", lambda latex, context: [])
    monkeypatch.setattr(repair, "_blocking_issues", lambda issues: list(issues))

    result = repair.repair_section_draft_if_possible(
        cwd=None,
        provider=_Provider(),
        runtime_mode="compatibility",
        user_prompt="original prompt",
        latex="bad draft",
        validation_issues=[original_issue],
        blocking_issues=[original_issue],
        draft_context=object(),
        validation_context=object(),
        min_citation_coverage=3,
        citation_map={"goodkey": {}},
        plot_assets_index={"assets": []},
        selected_sections=[],
        strict_claim_safe_prompt=False,
        citation_replacements={"old": "new"},
        dropped_citations={"dropped": 2},
        lane_notes=["initial note"],
        lane_type="initial_lane",
        fallback_used=False,
    )

    assert result.latex == "normalized retry"
    assert result.validation_issues == []
    assert result.blocking_issues == []
    assert result.lane_type == "retry_lane"
    assert result.fallback_used is True
    assert calls["kwargs"]["trace_stage"] == "section_writing_repair"
    assert "validation_issues.json" in calls["request"].user_prompt
    assert "Section writer draft was retried" in "\n".join(result.lane_notes)
    assert "retry note" in result.lane_notes
    assert "old->new" in "\n".join(result.lane_notes)
    assert "badkey->goodkey" in "\n".join(result.lane_notes)
    assert "ghost(1)" in "\n".join(result.lane_notes)
    assert "dropped(2)" in "\n".join(result.lane_notes)


def test_non_blocking_draft_records_alias_and_drop_notes_without_retry(monkeypatch) -> None:
    def fail_complete(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("repair model should not be called for non-blocking drafts")

    monkeypatch.setattr(repair, "_complete_with_runtime_mode", fail_complete)

    result = repair.repair_section_draft_if_possible(
        cwd=None,
        provider=_Provider(),
        runtime_mode="compatibility",
        user_prompt="prompt",
        latex="draft",
        validation_issues=[],
        blocking_issues=[],
        draft_context=object(),
        validation_context=object(),
        min_citation_coverage=1,
        citation_map={"new": {}},
        plot_assets_index={"assets": []},
        selected_sections=[],
        strict_claim_safe_prompt=True,
        citation_replacements={"old": "new"},
        dropped_citations={"unknown": 3},
        lane_notes=["base"],
        lane_type="lane",
        fallback_used=False,
    )

    joined = "\n".join(result.lane_notes)
    assert result.latex == "draft"
    assert result.lane_type == "lane"
    assert "Canonicalized citation-key aliases in section draft: old->new" in joined
    assert "Blocked unsupported citation keys in strict section draft: unknown(3)" in joined


def test_retry_plot_issue_gets_deterministic_post_processing(monkeypatch) -> None:
    original_issue = _Issue("plot_plan_not_reflected")
    validate_inputs: list[str] = []

    monkeypatch.setattr(
        repair,
        "_complete_with_runtime_mode",
        lambda *args, **kwargs: ("retry response", "retry_lane", False, ["retry note"]),
    )
    monkeypatch.setattr(repair, "extract_latex", lambda response: "retry latex")
    monkeypatch.setattr(repair, "normalize_section_draft", lambda latex, context: ("retry normalized", {}, {}))

    def fake_validate(latex: str, context: object) -> list[_Issue]:
        validate_inputs.append(latex)
        if latex == "stable repaired":
            return []
        return [original_issue]

    monkeypatch.setattr(repair, "validate_section_draft", fake_validate)
    monkeypatch.setattr(repair, "_blocking_issues", lambda issues: list(issues))
    monkeypatch.setattr(repair, "_inject_missing_plot_assets", lambda latex, issues, assets: "repaired")
    monkeypatch.setattr(repair, "_stabilize_figure_float_placement", lambda latex: "stable repaired")

    result = repair.repair_section_draft_if_possible(
        cwd=None,
        provider=_Provider(),
        runtime_mode="compatibility",
        user_prompt="prompt",
        latex="bad draft",
        validation_issues=[original_issue],
        blocking_issues=[original_issue],
        draft_context=object(),
        validation_context=object(),
        min_citation_coverage=1,
        citation_map={},
        plot_assets_index={"assets": [{"figure_id": "fig"}]},
        selected_sections=[],
        strict_claim_safe_prompt=False,
        citation_replacements={},
        dropped_citations={},
        lane_notes=[],
        lane_type="lane",
        fallback_used=False,
    )

    assert validate_inputs == ["retry normalized", "stable repaired"]
    assert result.latex == "stable repaired"
    assert result.validation_issues == []
    assert result.blocking_issues == []
    assert result.lane_type == "retry_lane"
    assert "deterministic post-processing" in "\n".join(result.lane_notes)
