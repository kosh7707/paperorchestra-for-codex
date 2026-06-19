from __future__ import annotations

import json
from html import unescape

from paperorchestra.engine import planning_payloads


def test_writer_brief_projects_claims_evidence_and_citation_guidance() -> None:
    brief = planning_payloads._writer_brief_from_planning(
        {
            "thesis": "Evidence-grounded alert triage.",
            "contribution_boundary": ["Scope claims to Java SAST."],
            "section_roles": [
                {
                    "section_title": "Method",
                    "role": "Explain the pipeline.",
                    "must_cover": ["legacy outline item"],
                    "must_not_claim": ["Do not claim universal soundness."],
                }
            ],
        },
        {
            "claims": [
                {
                    "target_section": "Method",
                    "authorial_claim": "The pipeline preserves recall while reducing review burden.",
                    "claim_type": "method",
                    "grounding": "source_material",
                    "risk": "medium",
                    "coverage_groups": ["recall", "review burden"],
                    "evidence_anchors": [
                        {
                            "evidence_excerpt": "TP suppression remains zero in the frozen run.",
                            "line_start": 10,
                            "line_end": 12,
                        }
                    ],
                }
            ]
        },
        {"placements": [{"target_section": "Method", "citation_keys": ["Smith2024"], "purpose": "contrast baseline"}]},
    )

    method = brief["section_roles"][0]
    claim = method["required_claims"][0]
    assert brief["thesis"] == "Evidence-grounded alert triage."
    assert method["must_cover"] == ["The pipeline preserves recall while reducing review burden."]
    assert claim["grounding"] == "technical_evidence"
    assert claim["supporting_evidence"] == [
        {"excerpt": "TP suppression remains zero in the frozen run.", "location": "lines 10-12"}
    ]
    assert brief["citation_guidance"] == [
        {"section": "Method", "citation_keys": ["Smith2024"], "purpose": "contrast baseline"}
    ]


def test_author_facing_writer_brief_block_renders_validated_json() -> None:
    block = planning_payloads._author_facing_writer_brief_block(
        {
            "thesis": "Build a scholarly draft.",
            "contribution_boundary": [],
            "section_roles": [],
            "citation_guidance": [],
            "authoring_rules": ["Write only scholarly paper prose."],
        }
    )

    assert '<DATA_BLOCK name="scholarly_authoring_brief">' in block
    payload = json.loads(unescape(block.split("\n", 1)[1].rsplit("</DATA_BLOCK>", 1)[0]))
    assert payload["thesis"] == "Build a scholarly draft."


def test_writer_brief_attaches_canonical_alias_claims_to_section_roles() -> None:
    brief = planning_payloads._writer_brief_from_planning(
        {
            "thesis": "Evidence-grounded alert triage.",
            "contribution_boundary": [],
            "section_roles": [
                {
                    "section_title": "Methodology",
                    "role": "Explain the pipeline.",
                    "must_cover": [],
                    "must_not_claim": [],
                }
            ],
        },
        {
            "claims": [
                {
                    "target_section": "System",
                    "authorial_claim": "The agent triage pipeline is evidence grounded.",
                    "claim_type": "method",
                    "grounding": "source_material",
                    "coverage_groups": [["agent", "triage"]],
                    "evidence_anchors": [{"evidence_excerpt": "pipeline evidence"}],
                }
            ]
        },
        {"placements": []},
    )

    method = brief["section_roles"][0]
    assert method["must_cover"] == ["The agent triage pipeline is evidence grounded."]
    assert method["required_claims"][0]["claim"] == "The agent triage pipeline is evidence grounded."


def test_filter_planning_payloads_uses_canonical_section_aliases() -> None:
    narrative = {
        "section_roles": [{"section_title": "System"}, {"section_title": "Related Work"}],
        "story_beats": [{"target_section": "System"}, {"target_section": "Related Work"}],
    }
    claim_map = {
        "claims": [
            {"id": "C1", "target_section": "System"},
            {"id": "C2", "target_section": "Related Work"},
        ]
    }
    citation_plan = {
        "placements": [
            {"claim_id": "C1", "target_section": "System"},
            {"claim_id": "C2", "target_section": "Related Work"},
        ]
    }

    filtered_narrative, filtered_claims, filtered_citations = planning_payloads._filter_planning_payloads_for_sections(
        narrative, claim_map, citation_plan, ["Methodology"]
    )

    assert filtered_narrative["section_roles"] == [{"section_title": "System"}]
    assert filtered_narrative["story_beats"] == [{"target_section": "System"}]
    assert filtered_claims["claims"] == [{"id": "C1", "target_section": "System"}]
    assert filtered_citations["placements"] == [{"claim_id": "C1", "target_section": "System"}]
