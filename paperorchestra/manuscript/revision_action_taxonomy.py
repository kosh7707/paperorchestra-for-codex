from __future__ import annotations


def _has_any(text: str, tokens: list[str]) -> bool:
    return any(token in text for token in tokens)


def _target_for_item(item: str) -> str:
    lowered = item.lower()
    if _has_any(lowered, ["proof", "theorem", "bound", "analysis", "guarantee", "security", "privacy"]):
        return "security_analysis"
    if _has_any(
        lowered,
        ["evaluation", "benchmark", "experiment", "measurement", "throughput", "latency", "dataset", "baseline"],
    ):
        return "implementation_results"
    if _has_any(lowered, ["citation", "bibliography", "prior", "related", "novelty", "literature"]):
        return "introduction_related_work"
    if _has_any(lowered, ["method", "construction", "interface", "protocol", "algorithm", "architecture", "model"]):
        return "proposed_method"
    return "discussion_limitations"


def _target_for_section_title(title: str) -> str:
    return _target_for_item(title)


def _action_type_for_item(item: str) -> str:
    lowered = item.lower()
    if _has_any(lowered, ["citation", "bibliography", "prior", "related"]):
        return "curate_and_verify_citations"
    if _has_any(lowered, ["proof", "theorem", "bound", "analysis", "guarantee"]):
        return "formalize_security_argument"
    if _has_any(lowered, ["protocol", "interface", "algorithm", "architecture", "model"]):
        return "specify_protocol_interface"
    if _has_any(
        lowered,
        ["evaluation", "benchmark", "experiment", "measurement", "throughput", "latency", "dataset", "baseline"],
    ):
        return "tighten_evaluation_scope"
    if _has_any(lowered, ["novelty", "comparison", "close prior"]):
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
