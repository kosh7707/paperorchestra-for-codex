from __future__ import annotations

from paperorchestra.manuscript.revision_action_taxonomy import _action_type_for_item, _priority_for_action, _target_for_item
from paperorchestra.manuscript.revision_action_templates import _patch_hunk_template


def test_revision_action_classification_targets_and_priorities() -> None:
    citation_item = "Related work lacks citation support for closest prior literature."
    method_item = "Architecture must specify protocol interface and model assumptions."
    eval_item = "Benchmark experiment must state dataset latency baseline."
    proof_item = "Security proof theorem needs a concrete bound."

    assert _target_for_item(citation_item) == "introduction_related_work"
    assert _target_for_item(method_item) == "proposed_method"
    assert _target_for_item(eval_item) == "implementation_results"
    assert _target_for_item(proof_item) == "security_analysis"
    assert _target_for_item("Tone down broad claims") == "discussion_limitations"

    assert _action_type_for_item(citation_item) == "curate_and_verify_citations"
    assert _action_type_for_item(method_item) == "specify_protocol_interface"
    assert _action_type_for_item(eval_item) == "tighten_evaluation_scope"
    assert _action_type_for_item(proof_item) == "formalize_security_argument"
    assert _action_type_for_item("Novelty comparison is weak") == "strengthen_novelty_positioning"

    assert _priority_for_action("curate_and_verify_citations", citation_item) == ("P0", "critical")
    assert _priority_for_action("specify_protocol_interface", method_item) == ("P1", "high")
    assert _priority_for_action("revise_exposition", "unsupported claim remains") == ("P1", "high")
    assert _priority_for_action("revise_exposition", "clarify paragraph") == ("P2", "medium")


def test_revision_patch_templates_preserve_manual_guidance_contract() -> None:
    proof = _patch_hunk_template("security_analysis", "formalize_security_argument", "proof missing")
    method = _patch_hunk_template("proposed_method", "specify_protocol_interface", "interface missing")
    citation = _patch_hunk_template("introduction_related_work", "curate_and_verify_citations", "citation missing")
    evaluation = _patch_hunk_template("implementation_results", "tighten_evaluation_scope", "scope missing")
    novelty = _patch_hunk_template("introduction_related_work", "strengthen_novelty_positioning", "novelty missing")
    default = _patch_hunk_template("discussion_limitations", "revise_exposition", "unclear text")

    assert proof["edit_kind"] == "manual_patch_draft"
    assert proof["anchor"] == r"\section{Security Analysis}"
    assert "Analysis statement" in proof["hunk_template"]
    assert "Method interface details" in method["hunk_template"]
    assert "verified citation keys" in citation["hunk_template"]
    assert "Evaluation scope" in evaluation["hunk_template"]
    assert "closest prior constructions" in novelty["hunk_template"]
    assert default["review_focus"] == "unclear text"
    assert default["anchor"] == r"\section{Discussion} or \section{Discussion and Limitations}"
