from __future__ import annotations

from typing import Any


def _section_anchor_for_target(target_area: str) -> str:
    return {
        "introduction_related_work": r"\section{Introduction} or \section{Related Work}",
        "proposed_method": r"\section{Method} or \section{Proposed Method}",
        "security_analysis": r"\section{Security Analysis}",
        "implementation_results": r"\section{Implementation and Results} or \section{Experiments}",
        "discussion_limitations": r"\section{Discussion} or \section{Discussion and Limitations}",
    }.get(target_area, r"\section{...}")


def _patch_hunk_template(target_area: str, action_type: str, review_item: str) -> dict[str, Any]:
    return {
        "anchor": _section_anchor_for_target(target_area),
        "edit_kind": "manual_patch_draft",
        "hunk_template": _hunk_template(action_type),
        "review_focus": review_item,
    }


def _hunk_template(action_type: str) -> str:
    if action_type == "formalize_security_argument":
        return (
            "@@ after theorem/proof/analysis paragraph @@\n"
            "- % informal proof sketch\n"
            "+ \\paragraph{Analysis statement.}\n"
            "+ Define the assumptions, resources, and notation used by the argument.\n"
            "+ State the exact theorem, guarantee, or bound (or explicitly relabel this as a proof sketch).\n"
            "+ Tie the notation back to the method section and stated assumptions.\n"
        )
    if action_type == "specify_protocol_interface":
        return (
            "@@ near the method/interface subsection @@\n"
            "- % high-level method/interface description\n"
            "+ \\paragraph{Method interface details.}\n"
            "+ Define inputs, outputs, state, configuration, assumptions, and failure conditions.\n"
            "+ State what breaks if the stated assumptions are violated.\n"
        )
    if action_type == "curate_and_verify_citations":
        return (
            "@@ at the cited claim sentence @@\n"
            "- Existing claim without grounded support.\n"
            "+ Narrow the claim to the measured setting and add verified citation keys from citation_map.json.\n"
            "+ If the claim is comparative, add the exact baseline/standard source that supports the comparison.\n"
        )
    if action_type == "tighten_evaluation_scope":
        return (
            "@@ in experiments/limitations section @@\n"
            "- Broad deployment claim.\n"
            "+ \\paragraph{Evaluation scope.}\n"
            "+ Clarify the measurement level and environment, then list workload, dataset, platform, and portability limits.\n"
        )
    if action_type == "strengthen_novelty_positioning":
        return (
            "@@ in related work or method intro @@\n"
            "- Generic novelty statement.\n"
            "+ Add a contrast paragraph naming the closest prior constructions and stating exactly what is new here.\n"
        )
    return (
        "@@ in the target section @@\n"
        "- Existing vague or incomplete paragraph.\n"
        "+ Replace it with grounded prose that addresses the cited review item directly and cites available evidence.\n"
    )
