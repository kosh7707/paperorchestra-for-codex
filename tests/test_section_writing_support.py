from __future__ import annotations

from paperorchestra.engine import section_writing_support as support
from paperorchestra.engine.section_writing_support import SectionDraftContext, SectionValidationContext


def test_normalize_section_draft_preserves_postprocess_order(monkeypatch) -> None:
    calls: list[str] = []

    def step(name):
        def _inner(latex, *args, **kwargs):
            calls.append(name)
            return f"{latex}|{name}"

        return _inner

    monkeypatch.setattr(support, "_preserve_all_except_sections", step("preserve_selected"))
    monkeypatch.setattr(support, "_preserve_existing_sections", step("preserve_intro_related"))
    monkeypatch.setattr(support, "_restore_missing_referenced_labels", step("restore_labels"))
    monkeypatch.setattr(support, "_ensure_bibliography_hook", step("bibliography_hook"))
    monkeypatch.setattr(support, "_normalize_generated_plot_paths", step("generated_plot_paths"))
    monkeypatch.setattr(support, "_normalize_source_figure_paths", step("source_figure_paths"))
    monkeypatch.setattr(support, "_ensure_generated_plot_usage", step("generated_plot_usage"))
    monkeypatch.setattr(support, "_stabilize_figure_float_placement", step("float_placement"))
    monkeypatch.setattr(support, "_remove_material_packet_sections", step("remove_material_packet"))
    monkeypatch.setattr(support, "_ensure_discussion_section_for_claim_boundaries", step("discussion_bounds"))
    monkeypatch.setattr(support, "_ensure_required_claim_scope_notes", step("claim_notes"))

    def canonicalize(latex, citation_map):
        calls.append("canonicalize_citations")
        return f"{latex}|canonicalize_citations", {"Alias": "Real"}

    def drop_unknown(latex, citation_map):
        calls.append("drop_unknown_citations")
        return f"{latex}|drop_unknown_citations", {"BadKey": 1}

    monkeypatch.setattr(support, "canonicalize_citation_keys", canonicalize)
    monkeypatch.setattr(support, "_drop_unknown_citation_keys", drop_unknown)

    latex, replacements, dropped = support.normalize_section_draft(
        "draft",
        SectionDraftContext(
            current_source="full manuscript",
            selected_sections=["Method"],
            intro_related_source="intro",
            template_content="template",
            citation_map={"Real": {}},
            plot_assets_index={"assets": []},
            figures_dir="figures",
            claim_map={},
            strict_claim_safe_prompt=False,
        ),
    )

    assert calls == [
        "preserve_selected",
        "restore_labels",
        "bibliography_hook",
        "generated_plot_paths",
        "source_figure_paths",
        "generated_plot_usage",
        "float_placement",
        "remove_material_packet",
        "discussion_bounds",
        "claim_notes",
        "canonicalize_citations",
        "drop_unknown_citations",
    ]
    assert replacements == {"Alias": "Real"}
    assert dropped == {"BadKey": 1}
    assert latex.endswith("|drop_unknown_citations")


def test_validate_section_draft_uses_selected_scope_and_filter(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    raw_issues = [object()]
    filtered_issues = [object()]

    def selected_template(latex, selected_sections):
        calls.append(("selected_template", selected_sections))
        return "selected body"

    def source_grounding(inputs):
        calls.append(("source_grounding", inputs["experimental_log"]))
        return "grounded log"

    def collect(subject, **kwargs):
        calls.append(("collect", subject))
        assert kwargs["experimental_log_text"] == "grounded log"
        assert kwargs["expected_section_titles"] == ["Method"]
        return raw_issues

    def filter_issues(issues, *, selected_sections):
        calls.append(("filter", selected_sections))
        assert issues is raw_issues
        return filtered_issues

    monkeypatch.setattr(support, "_selected_section_template", selected_template)
    monkeypatch.setattr(support, "_source_grounding_text", source_grounding)
    monkeypatch.setattr(support, "collect_paper_contract_issues", collect)
    monkeypatch.setattr(support, "_filter_section_scoped_issues", filter_issues)

    result = support.validate_section_draft(
        "full manuscript",
        SectionValidationContext(
            selected_sections=["Method"],
            citation_map={},
            figures_dir="figures",
            plot_manifest={},
            plot_assets_index={},
            inputs={"experimental_log": "log"},
            expected_section_titles=["Method"],
            narrative_plan={},
            claim_map={},
            citation_placement_plan={},
        ),
    )

    assert result is filtered_issues
    assert calls == [
        ("selected_template", ["Method"]),
        ("source_grounding", "log"),
        ("collect", "selected body"),
        ("filter", ["Method"]),
    ]


def test_normalize_section_draft_preserves_intro_related_when_not_section_scoped(monkeypatch) -> None:
    calls: list[str] = []

    def preserve_intro(latex, intro_related_source, *, section_names):
        calls.append("preserve_intro_related")
        assert intro_related_source == "intro source"
        assert section_names == ["Introduction", "Related Work"]
        return f"{latex}|intro"

    monkeypatch.setattr(support, "_preserve_existing_sections", preserve_intro)
    for name in [
        "_restore_missing_referenced_labels",
        "_ensure_bibliography_hook",
        "_normalize_generated_plot_paths",
        "_normalize_source_figure_paths",
        "_ensure_generated_plot_usage",
        "_stabilize_figure_float_placement",
        "_remove_material_packet_sections",
        "_ensure_discussion_section_for_claim_boundaries",
        "_ensure_required_claim_scope_notes",
    ]:
        monkeypatch.setattr(support, name, lambda latex, *args, **kwargs: latex)
    monkeypatch.setattr(support, "canonicalize_citation_keys", lambda latex, citation_map: (latex, {}))
    monkeypatch.setattr(support, "_drop_unknown_citation_keys", lambda latex, citation_map: (latex, {}))

    latex, _, _ = support.normalize_section_draft(
        "draft",
        SectionDraftContext(
            current_source=None,
            selected_sections=None,
            intro_related_source="intro source",
            template_content="template",
            citation_map={},
            plot_assets_index={},
            figures_dir=None,
            claim_map={},
            strict_claim_safe_prompt=False,
        ),
    )

    assert calls == ["preserve_intro_related"]
    assert latex == "draft|intro"
