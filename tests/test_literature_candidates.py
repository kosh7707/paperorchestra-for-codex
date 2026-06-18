from __future__ import annotations

from paperorchestra.research.literature_candidates import build_search_grounded_candidates


def test_mock_grounded_candidates_merge_sources_by_normalized_title() -> None:
    payload, notes = build_search_grounded_candidates(
        ["Noise Filtering", "Alert Triage"],
        macro_query_count=1,
        mode="mock",
    )

    assert notes == [
        "Mock grounded query completed: Noise Filtering",
        "Mock grounded query completed: Alert Triage",
    ]
    assert len(payload["macro_candidates"]) == 1
    assert len(payload["micro_candidates"]) == 1
    macro = payload["macro_candidates"][0]
    micro = payload["micro_candidates"][0]
    assert macro["title_guess"] == "Noise Filtering"
    assert macro["role_guess"] == "macro"
    assert macro["discovery_source"] == "semantic_scholar"
    assert macro["discovery_sources"] == ["semantic_scholar", "openalex"]
    assert micro["role_guess"] == "micro"
    assert micro["discovery_sources"] == ["semantic_scholar", "openalex"]


def test_mock_grounded_candidates_respect_cutoff() -> None:
    payload, notes = build_search_grounded_candidates(
        ["Too New"],
        macro_query_count=1,
        cutoff_date="2024-01-01",
        mode="mock",
    )

    assert payload == {"macro_candidates": [], "micro_candidates": []}
    assert notes == ["Mock grounded query completed: Too New"]
