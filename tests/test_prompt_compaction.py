from __future__ import annotations

from paperorchestra.engine import prompt_compaction as compact


def test_prompt_compaction_trims_outline_and_intro_related_plan() -> None:
    outline = {
        "section_plan": [
            {
                "section_title": "Intro",
                "subsections": [
                    {"subsection_title": "A", "content_bullets": ["one", "two"], "citation_hints": ["c1", "c2"]},
                    {"subsection_title": "B", "content_bullets": ["three"], "citation_hints": []},
                    {"subsection_title": "C", "content_bullets": ["drop"], "citation_hints": []},
                ],
            }
        ]
    }
    plan = {
        "introduction_strategy": {
            "hook_hypothesis": "Hook",
            "problem_gap_hypothesis": "Gap",
            "search_directions": ["one", "", "two", "three", "drop"],
        },
        "related_work_strategy": {"overview": "Overview", "subsections": [{"subsection_title": "RW"}] * 5},
    }

    assert compact._compact_outline_for_prompt(outline)["section_plan"][0]["subsections"] == [
        {"subsection_title": "A", "content_bullets": ["one"], "citation_hints": ["c1"]},
        {"subsection_title": "B", "content_bullets": ["three"], "citation_hints": []},
    ]
    assert len(compact._compact_intro_related_plan_for_prompt(plan)["related_work_strategy"]["subsections"]) == 4


def test_prompt_compaction_trims_plot_payloads_and_citation_map() -> None:
    long_title = "T" * 300
    long_abstract = "A" * 300
    citation_map = {
        "Alias2024": {"canonical_bibtex_key": "Real2024", "title": "Alias"},
        "Real2024": {
            "title": long_title,
            "abstract": long_abstract,
            "authors": ["a1", "a2", "a3", "a4", "a5"],
            "year": 2024,
            "venue": "Venue",
            "provenance": {"source": "seed"},
        },
    }

    plots = compact._compact_plot_manifest_for_prompt({"figures": [{"figure_id": "f", "title": long_title, "caption": long_title}]})
    assets = compact._compact_plot_assets_for_prompt({"assets": [{"figure_id": "f", "title": long_title, "caption": long_title}]})
    citations = compact._compact_citation_map_for_prompt(citation_map)

    assert "[...truncated for prompt budget...]" in plots["figures"][0]["title"]
    assert "[...truncated for prompt budget...]" in assets["assets"][0]["caption"]
    assert list(citations) == ["Real2024"]
    assert citations["Real2024"]["authors"] == ["a1", "a2", "a3", "a4"]
    assert "[...truncated for prompt budget...]" in citations["Real2024"]["abstract"]
