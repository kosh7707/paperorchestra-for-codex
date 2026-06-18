from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary_patterns import is_machine_control_prose
from paperorchestra.domains import get_domain


def generic_authorial_claim(claim: dict[str, Any]) -> str:
    claim_type = str(claim.get("claim_type") or "").strip().lower()
    grounding = str(claim.get("grounding") or "").strip().lower()
    target = str(claim.get("target_section") or "").strip().lower()
    if claim_type == "method" or "method" in target:
        return "The method description is limited to the construction, assumptions, and evidence stated for this paper."
    if claim_type in {"security", "proof"} or "security" in target:
        return "The analysis is limited to the stated assumptions, evidence, and proof obligations."
    if _is_benchmark_claim(claim_type, grounding, target):
        return (
            "The benchmark comparison is limited to the experimental log's measurements, "
            "implementation profiles, and message-size settings."
        )
    if claim_type == "limitation" or grounding == "human_boundary" or "discussion" in target:
        return "The paper's conclusions remain within the stated limitations, assumptions, and technical boundary and scope."
    if claim_type == "positioning" or grounding == "verified_citation":
        return "The introduction and related work position the paper against verified background and baseline literature."
    return "The statement is scoped to the evidence and assumptions presented in the paper."


def authorial_claim_text(claim: dict[str, Any]) -> str:
    explicit = str(claim.get("authorial_claim") or "").strip()
    if explicit and not is_machine_control_prose(explicit):
        return explicit
    legacy = str(claim.get("text") or "").strip()
    if legacy and not is_machine_control_prose(legacy):
        return legacy
    return generic_authorial_claim(claim)


def scope_note_text(claim: dict[str, Any]) -> str:
    explicit = str(claim.get("scope_note") or "").strip()
    if explicit and not is_machine_control_prose(explicit):
        return explicit
    claim_type = str(claim.get("claim_type") or "").strip().lower()
    grounding = str(claim.get("grounding") or "").strip().lower()
    target = str(claim.get("target_section") or "").strip().lower()
    base = _sentence(authorial_claim_text(claim))
    return base + get_domain().scope_tail(claim_type=claim_type, grounding=grounding, target_section=target)


def _is_benchmark_claim(claim_type: str, grounding: str, target: str) -> bool:
    return claim_type == "benchmark" or grounding == "experimental_log" or any(
        word in target for word in ("experiment", "result", "evaluation", "implementation")
    )


def _sentence(text: str) -> str:
    return text if not text or text.endswith(".") else text + "."
