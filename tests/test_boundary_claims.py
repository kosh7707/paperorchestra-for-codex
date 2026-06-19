from __future__ import annotations

from paperorchestra.core.boundary import (
    authorial_claim_text,
    normalized_claim_projection,
    normalized_coverage_groups,
    scope_note_text,
)
from paperorchestra.core import boundary
from paperorchestra.core import boundary_claims, boundary_control, boundary_sanitize


def test_boundary_facade_exports_all_public_symbols() -> None:
    assert sorted(boundary.__all__) == [
        "CONTROL_PROSE_PATTERNS",
        "_as_strings",
        "_walk_strings",
        "assert_author_facing_payload",
        "author_facing_payload_markers",
        "authorial_claim_text",
        "control_prose_markers",
        "generic_authorial_claim",
        "is_machine_control_prose",
        "is_material_packet_control_section_title",
        "is_material_packet_section_title",
        "normalized_claim_projection",
        "normalized_coverage_groups",
        "normalized_title",
        "projection_for_claims",
        "sanitize_author_facing_text",
        "scope_note_text",
    ]
    assert all(hasattr(boundary, name) for name in boundary.__all__)


def test_boundary_responsibility_modules_are_directly_importable() -> None:
    assert boundary_control.control_prose_markers("source boundary") == ["source_boundary"]
    assert boundary_claims.normalized_coverage_groups({"coverage_terms": ["x"]}) == [["x"]]
    assert boundary_sanitize.sanitize_author_facing_text("supplied packet") == "stated evidence"


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
