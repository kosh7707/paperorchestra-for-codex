from __future__ import annotations

from paperorchestra.manuscript import claim_validation


def test_claim_map_coverage_distinguishes_nearby_terms_from_keyword_stuffing() -> None:
    claim_map = {
        "claims": [
            {
                "id": "C1",
                "required": True,
                "target_section": "Method",
                "evidence_anchors": ["log"],
                "coverage_groups": [["agent", "triage"], ["recall", "preserving"]],
            }
        ]
    }
    covered = r"\section{Method} The agent triage loop is recall preserving under the benchmark assumptions."
    stuffed = r"\section{Method} Agent appears early. " + ("filler " * 80) + "Triage appears late. Recall alone. Preserving alone."

    assert claim_validation.check_claim_map_coverage(covered, claim_map) == []
    issues = claim_validation.check_claim_map_coverage(stuffed, claim_map)

    assert [issue.code for issue in issues] == ["required_claim_keyword_stuffing"]


def test_narrative_forbidden_claim_respects_boundary_negation() -> None:
    plan = {
        "section_roles": [
            {
                "section_title": "Discussion",
                "must_not_claim": ["the system is production ready"],
            }
        ]
    }
    bounded = r"\section{Discussion} The evaluation does not claim that the system is production ready."
    violating = r"\section{Discussion} The system is production ready for all deployments."

    assert claim_validation.check_narrative_section_roles(bounded, plan) == []
    issues = claim_validation.check_narrative_section_roles(violating, plan)

    assert [issue.code for issue in issues] == ["narrative_forbidden_claim_present"]


def test_prompt_meta_leakage_detects_visible_claim_map_metadata_but_ignores_comments() -> None:
    assert claim_validation.check_prompt_meta_leakage("% claim_id appears only in a comment") == []

    issues = claim_validation.check_prompt_meta_leakage(r"\section{Method} The claim_id field guided the draft.")

    assert [issue.code for issue in issues] == ["prompt_meta_leakage"]


def test_citation_placement_reports_missing_key_in_target_section() -> None:
    latex = r"\section{Method} We cite the wrong work \cite{Other}.\section{Results} No target citation."
    plan = {
        "placements": [
            {"claim_id": "C1", "target_section": "Method", "citation_keys": ["Needed"]}
        ]
    }

    issues = claim_validation.check_citation_placement(latex, plan)

    assert [issue.code for issue in issues] == ["citation_placement_missing"]
    assert "Needed" in issues[0].message


def test_narrative_section_roles_reports_missing_coverage_group_and_story_beat() -> None:
    plan = {
        "section_roles": [
            {
                "section_title": "Method",
                "coverage_requirements": [
                    {"authorial_claim": "Recall-preserving source triage", "coverage_groups": [["recall", "triage"]]},
                ],
            }
        ],
        "story_beats": [
            {"target_section": "Results", "beat": "Report precision trend", "coverage_groups": [["precision", "trend"]]},
        ],
    }
    latex = r"\section{Method} The system discusses recall only. \section{Results} The experiment reports precision only."

    issues = claim_validation.check_narrative_section_roles(latex, plan)

    assert [issue.code for issue in issues] == [
        "narrative_section_role_missing",
        "narrative_story_beat_missing",
    ]
    assert "Recall-preserving source triage" in issues[0].message
    assert "Report precision trend" in issues[1].message


def test_claim_validation_matches_system_and_evaluation_aliases() -> None:
    claim_map = {
        "claims": [
            {
                "id": "C1",
                "required": True,
                "target_section": "System",
                "coverage_groups": [["agent", "triage"]],
                "evidence_anchors": ["method evidence"],
            },
            {
                "id": "C2",
                "required": True,
                "target_section": "Evaluation Design",
                "coverage_groups": [["benchmark", "measurements"]],
                "evidence_anchors": ["evaluation evidence"],
            },
        ]
    }
    latex = (
        r"\section{Methodology} The agent triage pipeline is described."
        r"\section{Experiment Setup} The benchmark measurements are scoped."
    )

    assert claim_validation.check_claim_map_coverage(latex, claim_map) == []
