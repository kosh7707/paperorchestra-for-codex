from __future__ import annotations

from typing import Any


def _target_for_item(item: str) -> str:
    lowered = item.lower()
    if any(token in lowered for token in ["proof", "theorem", "bound", "analysis", "guarantee", "security", "privacy"]):
        return "security_analysis"
    if any(token in lowered for token in ["evaluation", "benchmark", "experiment", "measurement", "throughput", "latency", "dataset", "baseline"]):
        return "implementation_results"
    if any(token in lowered for token in ["citation", "bibliography", "prior", "related", "novelty", "literature"]):
        return "introduction_related_work"
    if any(token in lowered for token in ["method", "construction", "interface", "protocol", "algorithm", "architecture", "model"]):
        return "proposed_method"
    return "discussion_limitations"


def _target_for_section_title(title: str) -> str:
    return _target_for_item(title)


def _action_type_for_item(item: str) -> str:
    lowered = item.lower()
    if any(token in lowered for token in ["citation", "bibliography", "prior", "related"]):
        return "curate_and_verify_citations"
    if any(token in lowered for token in ["proof", "theorem", "bound", "analysis", "guarantee"]):
        return "formalize_security_argument"
    if any(token in lowered for token in ["protocol", "interface", "algorithm", "architecture", "model"]):
        return "specify_protocol_interface"
    if any(token in lowered for token in ["evaluation", "benchmark", "experiment", "measurement", "throughput", "latency", "dataset", "baseline"]):
        return "tighten_evaluation_scope"
    if any(token in lowered for token in ["novelty", "comparison", "close prior"]):
        return "strengthen_novelty_positioning"
    return "revise_exposition"


def _priority_for_action(action_type: str, item: str) -> tuple[str, str]:
    lowered = item.lower()
    if action_type in {"curate_and_verify_citations", "formalize_security_argument"}:
        return "P0", "critical"
    if action_type in {"specify_protocol_interface", "strengthen_novelty_positioning"}:
        return "P1", "high"
    if "unsupported" in lowered or "invalid" in lowered:
        return "P1", "high"
    return "P2", "medium"


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


def _section_anchor_for_target(target_area: str) -> str:
    return {
        "introduction_related_work": r"\section{Introduction} or \section{Related Work}",
        "proposed_method": r"\section{Method} or \section{Proposed Method}",
        "security_analysis": r"\section{Security Analysis}",
        "implementation_results": r"\section{Implementation and Results} or \section{Experiments}",
        "discussion_limitations": r"\section{Discussion} or \section{Discussion and Limitations}",
    }.get(target_area, r"\section{...}")


def _patch_hunk_template(target_area: str, action_type: str, review_item: str) -> dict[str, Any]:
    anchor = _section_anchor_for_target(target_area)
    if action_type == "formalize_security_argument":
        snippet = (
            "@@ after theorem/proof/analysis paragraph @@\n"
            "- % informal proof sketch\n"
            "+ \\paragraph{Analysis statement.}\n"
            "+ Define the assumptions, resources, and notation used by the argument.\n"
            "+ State the exact theorem, guarantee, or bound (or explicitly relabel this as a proof sketch).\n"
            "+ Tie the notation back to the method section and stated assumptions.\n"
        )
    elif action_type == "specify_protocol_interface":
        snippet = (
            "@@ near the method/interface subsection @@\n"
            "- % high-level method/interface description\n"
            "+ \\paragraph{Method interface details.}\n"
            "+ Define inputs, outputs, state, configuration, assumptions, and failure conditions.\n"
            "+ State what breaks if the stated assumptions are violated.\n"
        )
    elif action_type == "curate_and_verify_citations":
        snippet = (
            "@@ at the cited claim sentence @@\n"
            "- Existing claim without grounded support.\n"
            "+ Narrow the claim to the measured setting and add verified citation keys from citation_map.json.\n"
            "+ If the claim is comparative, add the exact baseline/standard source that supports the comparison.\n"
        )
    elif action_type == "tighten_evaluation_scope":
        snippet = (
            "@@ in experiments/limitations section @@\n"
            "- Broad deployment claim.\n"
            "+ \\paragraph{Evaluation scope.}\n"
            "+ Clarify the measurement level and environment, then list workload, dataset, platform, and portability limits.\n"
        )
    elif action_type == "strengthen_novelty_positioning":
        snippet = (
            "@@ in related work or method intro @@\n"
            "- Generic novelty statement.\n"
            "+ Add a contrast paragraph naming the closest prior constructions and stating exactly what is new here.\n"
        )
    else:
        snippet = (
            "@@ in the target section @@\n"
            "- Existing vague or incomplete paragraph.\n"
            "+ Replace it with grounded prose that addresses the cited review item directly and cites available evidence.\n"
        )
    return {
        "anchor": anchor,
        "edit_kind": "manual_patch_draft",
        "hunk_template": snippet,
        "review_focus": review_item,
    }
