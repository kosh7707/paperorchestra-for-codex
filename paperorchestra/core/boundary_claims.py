from __future__ import annotations

from typing import Any

from paperorchestra.core.boundary_patterns import is_machine_control_prose
from paperorchestra.domains import get_domain


def _as_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def normalized_coverage_groups(claim: dict[str, Any]) -> list[list[str]]:
    groups = claim.get("coverage_groups")
    if isinstance(groups, list):
        normalized: list[list[str]] = []
        for group in groups:
            terms = _as_strings(group) if isinstance(group, list) else _as_strings([group])
            if terms:
                normalized.append(terms)
        if normalized:
            return normalized
    terms = _as_strings(claim.get("coverage_terms"))
    return [[term] for term in terms]


def generic_authorial_claim(claim: dict[str, Any]) -> str:
    claim_type = str(claim.get("claim_type") or "").strip().lower()
    grounding = str(claim.get("grounding") or "").strip().lower()
    target = str(claim.get("target_section") or "").strip().lower()
    if claim_type == "method" or "method" in target:
        return "The method description is limited to the construction, assumptions, and evidence stated for this paper."
    if claim_type in {"security", "proof"} or "security" in target:
        return "The analysis is limited to the stated assumptions, evidence, and proof obligations."
    if claim_type == "benchmark" or grounding == "experimental_log" or any(
        word in target for word in ("experiment", "result", "evaluation", "implementation")
    ):
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
    base = authorial_claim_text(claim)
    if base and not base.endswith("."):
        base += "."
    return base + get_domain().scope_tail(claim_type=claim_type, grounding=grounding, target_section=target)


def normalized_claim_projection(claim: dict[str, Any]) -> dict[str, Any]:
    coverage_groups = normalized_coverage_groups(claim)
    return {
        "id": str(claim.get("id") or ""),
        "target_section": str(claim.get("target_section") or ""),
        "claim_type": claim.get("claim_type"),
        "grounding": claim.get("grounding"),
        "required": bool(claim.get("required", True)),
        "risk": claim.get("risk"),
        "authorial_claim": authorial_claim_text(claim),
        "scope_note": scope_note_text(claim),
        "coverage_groups": coverage_groups,
        "coverage_terms": sorted({term for group in coverage_groups for term in group}),
        "machine_obligation": str(claim.get("machine_obligation") or "").strip(),
    }


def projection_for_claims(claims: Any) -> list[dict[str, Any]]:
    if not isinstance(claims, list):
        return []
    return [normalized_claim_projection(claim) for claim in claims if isinstance(claim, dict)]
