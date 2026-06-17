from __future__ import annotations

from paperorchestra.manuscript import validator


def test_validator_reexports_claim_validation_surface() -> None:
    import paperorchestra.manuscript.claim_validation as claim_validation
    from paperorchestra.manuscript.validation_types import ValidationIssue

    assert validator.ValidationIssue is ValidationIssue
    assert validator.check_prompt_meta_leakage is claim_validation.check_prompt_meta_leakage
    assert validator.check_claim_map_coverage is claim_validation.check_claim_map_coverage
    assert validator.check_citation_placement is claim_validation.check_citation_placement
    assert validator.check_narrative_section_roles is claim_validation.check_narrative_section_roles


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

    assert validator.check_claim_map_coverage(covered, claim_map) == []
    issues = validator.check_claim_map_coverage(stuffed, claim_map)

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

    assert validator.check_narrative_section_roles(bounded, plan) == []
    issues = validator.check_narrative_section_roles(violating, plan)

    assert [issue.code for issue in issues] == ["narrative_forbidden_claim_present"]


def test_prompt_meta_leakage_detects_visible_claim_map_metadata_but_ignores_comments() -> None:
    assert validator.check_prompt_meta_leakage("% claim_id appears only in a comment") == []

    issues = validator.check_prompt_meta_leakage(r"\section{Method} The claim_id field guided the draft.")

    assert [issue.code for issue in issues] == ["prompt_meta_leakage"]


def test_citation_placement_reports_missing_key_in_target_section() -> None:
    latex = r"\section{Method} We cite the wrong work \cite{Other}.\section{Results} No target citation."
    plan = {
        "placements": [
            {"claim_id": "C1", "target_section": "Method", "citation_keys": ["Needed"]}
        ]
    }

    issues = validator.check_citation_placement(latex, plan)

    assert [issue.code for issue in issues] == ["citation_placement_missing"]
    assert "Needed" in issues[0].message
