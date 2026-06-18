from __future__ import annotations


def _done_criteria(action_type: str) -> list[str]:
    if action_type == "curate_and_verify_citations":
        return [
            "Add or import real BibTeX/metadata for the cited prior work.",
            "Ensure all claims in the revised section cite verified or curated entries.",
            "Regenerate citation_map.json/references.bib and run review/eval artifacts again.",
        ]
    if action_type == "formalize_security_argument":
        return [
            "State theorem, model, and assumptions explicitly.",
            "Provide a concrete bound, guarantee, or clearly label a proof sketch.",
            "Check notation consistency against the method section.",
        ]
    if action_type == "specify_protocol_interface":
        return [
            "Define all method inputs, outputs, state variables, and failure conditions.",
            "State what breaks if the deployment violates the stated assumptions.",
        ]
    if action_type == "tighten_evaluation_scope":
        return [
            "Separate primitive-level measurements from end-to-end deployment claims.",
            "List environment, message-size, associated-data, and platform limitations.",
        ]
    return ["Revise the target section with grounded text and rerun review."]
