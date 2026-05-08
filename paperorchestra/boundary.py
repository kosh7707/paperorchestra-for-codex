from __future__ import annotations

import re
from typing import Any

from .domains import get_domain

CONTROL_PROSE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("benchmark_narrative_instruction", re.compile(r"\bbenchmark narrative must report\b", re.IGNORECASE)),
    ("draft_must_preserve", re.compile(r"\bthe draft must preserve\b", re.IGNORECASE)),
    ("source_grounded_control", re.compile(r"\bsource[-\s]*grounded\b", re.IGNORECASE)),
    ("source_boundary", re.compile(r"\bsource boundary\b", re.IGNORECASE)),
    ("supplied_source", re.compile(r"\bsupplied source\b", re.IGNORECASE)),
    ("provided_source", re.compile(r"\bprovided source\b", re.IGNORECASE)),
    ("supplied_material", re.compile(r"\bsupplied material\b", re.IGNORECASE)),
    ("provided_material", re.compile(r"\bprovided material\b", re.IGNORECASE)),
    ("supplied_technical_material", re.compile(r"\bsupplied\s+(?:technical\s+)?materials?\b", re.IGNORECASE)),
    ("provided_technical_material", re.compile(r"\bprovided\s+(?:technical\s+)?materials?\b", re.IGNORECASE)),
    (
        "available_source_artifact",
        re.compile(
            r"(?<!universe of )\bavailable\s+(?:source\s+)?(?:materials?|logs?|files?|artifacts?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reviewable_artifact_availability",
        re.compile(
            r"\breviewable\s+(?:figure\s+)?(?:files?|logs?|materials?|artifacts?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "figure_availability_narration",
        re.compile(
            r"\bno\s+(?:reviewable\s+)?figures?\s+because\s+no\s+(?:reviewable\s+)?(?:figure\s+)?(?:files?|assets?)\b|\bno\s+reviewable\s+figure\s+files\b",
            re.IGNORECASE,
        ),
    ),
    ("source_material", re.compile(r"\bsource material\b", re.IGNORECASE)),
    ("supplied_technical_evidence", re.compile(r"\bsupplied technical evidence\b", re.IGNORECASE)),
    ("provided_technical_evidence", re.compile(r"\bprovided technical evidence\b", re.IGNORECASE)),
    ("supplied_evidence", re.compile(r"\b(?:supplied|provided)\s+evidence\b", re.IGNORECASE)),
    ("supplied_theorem_statement", re.compile(r"\b(?:supplied|provided)\s+theorem\s+statements?\b", re.IGNORECASE)),
    (
        "source_artifact_reference",
        re.compile(
            r"\b(?:(?:supplied|provided)\s+(?:materials?|sources?|files?|analyses|analysis|logs?)|available\s+(?:materials?|sources?|files?|logs?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "supplied_packet_artifact",
        re.compile(
            r"\b(?:supplied|provided)\s+packet\b|\b(?:(?:supplied|provided)\s+)?(?:method|construction|proof|benchmark|empirical|review|source|material)\s+packet\b|\b(?:following|specified\s+in|as\s+specified\s+in)\s+the\s+packet\b",
            re.IGNORECASE,
        ),
    ),
    (
        "supplied_source_or_log_artifact",
        re.compile(
            r"\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b",
            re.IGNORECASE,
        ),
    ),
    ("manuscript_plan", re.compile(r"\bmanuscript\s+plan\b", re.IGNORECASE)),
    ("human_provided", re.compile(r"\bhuman[-\s]*provided\b", re.IGNORECASE)),
    ("external_claim_guardrail", re.compile(r"\bdoes not add an external claim\b|\bexternal[-\s]*claim guardrails?\b", re.IGNORECASE)),
    (
        "claim_boundary_control",
        re.compile(r"\bclaim[_\s-]*boundar(?:y|ies)\s+(?:control|guardrail|obligation|packet)\b", re.IGNORECASE),
    ),
    ("claim_map_artifact", re.compile(r"\bclaim[_\s-]*maps?(?:\.json)?\b", re.IGNORECASE)),
    ("narrative_plan_artifact", re.compile(r"\bnarrative[_\s-]*plans?(?:\.json)?\b", re.IGNORECASE)),
    (
        "writer_brief_artifact",
        re.compile(
            r"\bauthor[_\s-]*facing[_\s-]*writer[_\s-]*brief(?:\.json)?\b|\bwriter[_\s-]*brief(?:\.json)?\b",
            re.IGNORECASE,
        ),
    ),
    ("prompt_instruction", re.compile(r"\bprompt instructions?\b", re.IGNORECASE)),
    ("generation_pipeline", re.compile(r"\bgeneration pipeline\b", re.IGNORECASE)),
)


def control_prose_markers(text: str | None) -> list[str]:
    if not text:
        return []
    return [name for name, pattern in CONTROL_PROSE_PATTERNS if pattern.search(str(text))]


def is_machine_control_prose(text: str | None) -> bool:
    return bool(control_prose_markers(text))


def sanitize_author_facing_text(text: str | None, *, fallback: str = "") -> str:
    value = str(text or "").strip()
    if not value:
        return fallback
    replacements: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bhuman[-\s]*provided\b", re.IGNORECASE), "the paper's"),
        (
            re.compile(
                r"\b(?:supplied|provided)\s+packet\b|\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|review|source|material)\s+packet\b",
                re.IGNORECASE,
            ),
            "stated evidence",
        ),
        (
            re.compile(
                r"\b(?:supplied|provided)\s+(?:proof|benchmark|empirical|measurement|review)\s+(?:source|logs?)\b",
                re.IGNORECASE,
            ),
            "stated evidence",
        ),
        (re.compile(r"\bfollowing\s+the\s+packet\b", re.IGNORECASE), "Based on the stated evidence"),
        (re.compile(r"\b(?:as\s+)?specified\s+in\s+the\s+packet\b", re.IGNORECASE), "According to the stated evidence"),
        (re.compile(r"\b(?:(?:supplied|provided)\s+)?benchmark\s+packet\b", re.IGNORECASE), "benchmark evidence"),
        (re.compile(r"\b(?:(?:supplied|provided)\s+)?empirical\s+packet\b", re.IGNORECASE), "empirical evidence"),
        (re.compile(r"\b(?:(?:supplied|provided)\s+)?review\s+packet\b", re.IGNORECASE), "reviewed evidence"),
        (
            re.compile(
                r"\b(?:method|construction|proof|benchmark|empirical|review|source|material)\s+packet\b",
                re.IGNORECASE,
            ),
            "stated evidence",
        ),
        (re.compile(r"\bsupplied\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided\s+technical\s+materials?\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsupplied technical evidence\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided technical evidence\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided)\s+evidence\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided)\s+theorem\s+statements?\b", re.IGNORECASE), "theorem statements"),
        (re.compile(r"\bsupplied source material\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided source material\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bsource material\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\b(?:supplied|provided|available)\s+logs?\b", re.IGNORECASE), "measurement log"),
        (re.compile(r"\bavailable\s+(?:materials?|sources?|files?)\b", re.IGNORECASE), "stated evidence"),
        (
            re.compile(r"\b(?:supplied|provided)\s+(?:files?|analyses|analysis)\b", re.IGNORECASE),
            "stated evidence",
        ),
        (re.compile(r"\bsupplied materials?\b", re.IGNORECASE), "stated evidence"),
        (re.compile(r"\bprovided materials?\b", re.IGNORECASE), "stated evidence"),
        (
            re.compile(
                r"\bno\s+reviewable\s+figure\s+files\s+were\s+available\b|\breviewable\s+figure\s+files\s+were\s+not\s+available\b",
                re.IGNORECASE,
            ),
            "figures are outside this draft's current scope",
        ),
        (
            re.compile(r"\bavailable\s+(?:source\s+)?(?:materials?|logs?|files?|artifacts?)\b", re.IGNORECASE),
            "stated evidence",
        ),
        (re.compile(r"\bsource boundaries\b", re.IGNORECASE), "scope boundaries"),
        (re.compile(r"\bsource boundary\b", re.IGNORECASE), "scope boundary"),
        (re.compile(r"\bclaim boundaries\b", re.IGNORECASE), "technical boundary and scope"),
        (re.compile(r"\bmanuscript\s+plan\b", re.IGNORECASE), "paper outline"),
        (re.compile(r"\b(?:already\s+)?supplied\s+with\s+the\s+stated\s+evidence\b", re.IGNORECASE), "stated in the evidence"),
    )
    rewritten = value
    for pattern, replacement in replacements:
        rewritten = pattern.sub(replacement, rewritten)
    if not control_prose_markers(rewritten):
        return rewritten
    return fallback or "State evidence limits as ordinary scholarly assumptions, scope, and limitations."


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


def _walk_strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path, value)]
    if isinstance(value, dict):
        found: list[tuple[str, str]] = []
        for key, child in value.items():
            found.extend(_walk_strings(child, f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value):
            found.extend(_walk_strings(child, f"{path}[{index}]"))
        return found
    return []


def author_facing_payload_markers(payload: Any) -> list[dict[str, str]]:
    markers: list[dict[str, str]] = []
    for path, text in _walk_strings(payload):
        for marker in control_prose_markers(text):
            markers.append({"path": path, "marker": marker})
    return markers


def assert_author_facing_payload(payload: Any, *, label: str = "author-facing payload") -> None:
    markers = author_facing_payload_markers(payload)
    if markers:
        details = ", ".join(f"{item['path']}:{item['marker']}" for item in markers[:8])
        raise ValueError(f"{label} contains machine/control prose markers: {details}")


def normalized_title(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def is_material_packet_section_title(title: str | None) -> bool:
    normalized = normalized_title(title)
    if not normalized:
        return False
    if normalized == "00 core macros":
        return True
    if normalized == "author notes for positioning and framing":
        return True
    if re.fullmatch(r"claim boundaries(?: for (?:the )?.+ draft)?", normalized):
        return True
    if re.fullmatch(r"author notes(?: for .+)?", normalized):
        return True
    return False


def is_material_packet_control_section_title(title: str | None) -> bool:
    normalized = normalized_title(title)
    return is_material_packet_section_title(normalized) and normalized != "00 core macros"
