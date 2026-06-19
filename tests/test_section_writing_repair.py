from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperorchestra.engine import section_writing_repair as repair
from paperorchestra.engine import section_writing_repair_retry as retry
from paperorchestra.engine.section_writing_repair_bridge import can_bridge_retry_citation_coverage


@dataclass(frozen=True)
class _Issue:
    code: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code}


class _Provider:
    name = "test-provider"


def _repair_kwargs(issue: _Issue | None = None, **overrides: Any) -> dict[str, Any]:
    issues = [issue] if issue else []
    kwargs: dict[str, Any] = {
        "cwd": None,
        "provider": _Provider(),
        "runtime_mode": "compatibility",
        "user_prompt": "prompt",
        "latex": "bad draft" if issue else "draft",
        "validation_issues": issues,
        "blocking_issues": issues,
        "draft_context": object(),
        "validation_context": object(),
        "min_citation_coverage": 1,
        "citation_map": {},
        "plot_assets_index": {"assets": []},
        "selected_sections": [],
        "strict_claim_safe_prompt": False,
        "citation_replacements": {},
        "dropped_citations": {},
        "lane_notes": [],
        "lane_type": "lane",
        "fallback_used": False,
    }
    kwargs.update(overrides)
    return kwargs


def _stub_retry_generation(monkeypatch, *, normalized: str = "retry normalized", issues: list[_Issue] | None = None) -> None:
    monkeypatch.setattr(
        retry,
        "_complete_with_runtime_mode",
        lambda *args, **kwargs: ("retry response", "retry_lane", False, []),
    )
    monkeypatch.setattr(retry, "extract_latex", lambda response: "retry latex")
    monkeypatch.setattr(retry, "normalize_section_draft", lambda latex, context: (normalized, {}, {}))
    monkeypatch.setattr(retry, "validate_section_draft", lambda latex, context: list(issues or []))
    monkeypatch.setattr(retry, "_blocking_issues", lambda values: list(values))


def test_repairable_section_issue_retries_and_records_retry_notes(monkeypatch) -> None:
    original_issue = _Issue("expected_section_too_shallow")
    calls: dict[str, Any] = {}

    def fake_complete(request: Any, **kwargs: Any) -> tuple[str, str, bool, list[str]]:
        calls["request"] = request
        calls["kwargs"] = kwargs
        return "retry response", "retry_lane", True, ["retry note"]

    monkeypatch.setattr(retry, "_complete_with_runtime_mode", fake_complete)
    monkeypatch.setattr(retry, "extract_latex", lambda response: "retry latex")
    monkeypatch.setattr(
        retry,
        "normalize_section_draft",
        lambda latex, context: ("normalized retry", {"badkey": "goodkey"}, {"ghost": 1}),
    )
    monkeypatch.setattr(retry, "validate_section_draft", lambda latex, context: [])
    monkeypatch.setattr(retry, "_blocking_issues", lambda issues: list(issues))

    result = repair.repair_section_draft_if_possible(
        **_repair_kwargs(
            original_issue,
            user_prompt="original prompt",
            min_citation_coverage=3,
            citation_map={"goodkey": {}},
            citation_replacements={"old": "new"},
            dropped_citations={"dropped": 2},
            lane_notes=["initial note"],
            lane_type="initial_lane",
        )
    )

    joined = "\n".join(result.lane_notes)
    assert result.latex == "normalized retry"
    assert result.validation_issues == []
    assert result.blocking_issues == []
    assert result.lane_type == "retry_lane"
    assert result.fallback_used is True
    assert calls["kwargs"]["trace_stage"] == "section_writing_repair"
    assert "validation_issues.json" in calls["request"].user_prompt
    assert "Section writer draft was retried" in joined
    assert "retry note" in result.lane_notes
    assert "old->new" in joined
    assert "badkey->goodkey" in joined
    assert "ghost(1)" in joined
    assert "dropped(2)" in joined


def test_non_blocking_draft_records_alias_and_drop_notes_without_retry(monkeypatch) -> None:
    def fail_complete(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("repair model should not run")

    monkeypatch.setattr(retry, "_complete_with_runtime_mode", fail_complete)

    result = repair.repair_section_draft_if_possible(
        **_repair_kwargs(
            citation_map={"new": {}},
            strict_claim_safe_prompt=True,
            citation_replacements={"old": "new"},
            dropped_citations={"unknown": 3},
            lane_notes=["base"],
        )
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
        retry,
        "_complete_with_runtime_mode",
        lambda *args, **kwargs: ("retry response", "retry_lane", False, ["retry note"]),
    )
    monkeypatch.setattr(retry, "extract_latex", lambda response: "retry latex")
    monkeypatch.setattr(retry, "normalize_section_draft", lambda latex, context: ("retry normalized", {}, {}))

    def fake_validate(latex: str, context: object) -> list[_Issue]:
        validate_inputs.append(latex)
        return [] if latex == "stable repaired" else [original_issue]

    monkeypatch.setattr(retry, "validate_section_draft", fake_validate)
    monkeypatch.setattr(retry, "_blocking_issues", lambda issues: list(issues))
    monkeypatch.setattr(retry, "_inject_missing_plot_assets", lambda latex, issues, assets: "repaired")
    monkeypatch.setattr(retry, "_stabilize_figure_float_placement", lambda latex: "stable repaired")

    result = repair.repair_section_draft_if_possible(
        **_repair_kwargs(original_issue, plot_assets_index={"assets": [{"figure_id": "fig"}]})
    )

    assert validate_inputs == ["retry normalized", "stable repaired"]
    assert result.latex == "stable repaired"
    assert result.validation_issues == []
    assert result.blocking_issues == []
    assert result.lane_type == "retry_lane"
    assert "deterministic post-processing" in "\n".join(result.lane_notes)


def test_retry_citation_coverage_issue_can_bridge_related_work(monkeypatch) -> None:
    citation_issue = _Issue("citation_coverage_insufficient")
    validate_inputs: list[str] = []
    _stub_retry_generation(monkeypatch, issues=[citation_issue])

    def fake_validate(latex: str, context: object) -> list[_Issue]:
        validate_inputs.append(latex)
        return [] if latex == "bridged retry" else [citation_issue]

    monkeypatch.setattr(retry, "validate_section_draft", fake_validate)
    monkeypatch.setattr(retry, "_ensure_minimum_citation_coverage", lambda *args, **kwargs: "bridged retry")

    result = repair.repair_section_draft_if_possible(
        **_repair_kwargs(
            citation_issue,
            min_citation_coverage=2,
            citation_map={"a": {}, "b": {}},
            selected_sections=["Related Work"],
        )
    )

    assert validate_inputs == ["retry normalized", "bridged retry"]
    assert result.latex == "bridged retry"
    assert result.validation_issues == []
    assert result.blocking_issues == []
    assert result.lane_type == "retry_lane"


def test_retry_citation_bridge_policy_is_related_work_scoped() -> None:
    citation_issue = _Issue("citation_coverage_insufficient")

    assert can_bridge_retry_citation_coverage([citation_issue], [])
    assert can_bridge_retry_citation_coverage([citation_issue], ["Related Work"])
    assert can_bridge_retry_citation_coverage([citation_issue], ["Background and Related Work"])
    assert not can_bridge_retry_citation_coverage([citation_issue], ["Method"])
    assert not can_bridge_retry_citation_coverage([citation_issue, _Issue("plot_plan_not_reflected")], ["Related Work"])


def test_retry_citation_coverage_bridge_ignores_non_citation_failures(monkeypatch) -> None:
    shallow_issue = _Issue("expected_section_too_shallow")
    _stub_retry_generation(monkeypatch, issues=[shallow_issue])
    monkeypatch.setattr(
        retry,
        "_ensure_minimum_citation_coverage",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bridge must not run")),
    )

    result = repair.repair_section_draft_if_possible(
        **_repair_kwargs(shallow_issue, min_citation_coverage=2, selected_sections=["Related Work"], lane_notes=["base"])
    )

    assert result.latex == "bad draft"
    assert result.blocking_issues == [shallow_issue]
    assert result.lane_type == "lane"
