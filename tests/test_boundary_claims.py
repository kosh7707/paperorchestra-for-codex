from __future__ import annotations

from paperorchestra.core.boundary import (
    authorial_claim_text,
    normalized_claim_projection,
    normalized_coverage_groups,
    scope_note_text,
)


def test_normalized_coverage_groups_preserves_grouping_and_falls_back_to_terms() -> None:
    assert normalized_coverage_groups({"coverage_groups": [["precision", "recall"], "cost"]}) == [
        ["precision", "recall"],
        ["cost"],
    ]
    assert normalized_coverage_groups({"coverage_terms": ["source", " sink ", ""]}) == [["source"], ["sink"]]


def test_authorial_claim_text_rejects_machine_control_prose() -> None:
    claim = {
        "authorial_claim": "This sentence preserves the source boundary without adding a new external claim.",
        "text": "The pipeline triages alerts under the stated assumptions.",
    }

    assert authorial_claim_text(claim) == "The pipeline triages alerts under the stated assumptions."


def test_scope_note_appends_domain_scope_tail_to_authorial_claim() -> None:
    note = scope_note_text({"claim_type": "method", "authorial_claim": "The method uses evidence-grounded triage"})

    assert note.startswith("The method uses evidence-grounded triage.")
    assert "limited to the method" in note.lower()


def test_normalized_claim_projection_sorts_flattened_coverage_terms() -> None:
    projection = normalized_claim_projection(
        {
            "id": "C1",
            "target_section": "Evaluation",
            "claim_type": "benchmark",
            "coverage_groups": [["recall", "precision"], ["cost"]],
            "machine_obligation": "  verify metrics  ",
        }
    )

    assert projection["coverage_terms"] == ["cost", "precision", "recall"]
    assert projection["machine_obligation"] == "verify metrics"
