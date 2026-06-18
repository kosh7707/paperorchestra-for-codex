from __future__ import annotations

import re

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
