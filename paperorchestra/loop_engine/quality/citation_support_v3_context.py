from __future__ import annotations

from typing import Any


def v3_case_identity(cases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(str(case.get("id")), str(case.get("key"))) for case in cases]


def v3_case_context_projection(case: dict[str, Any]) -> dict[str, str]:
    resolution = case.get("resolution") if isinstance(case.get("resolution"), dict) else {}
    comparable_target = case.get("target")
    if resolution.get("action") == "weaken_claim" and resolution.get("original_target"):
        comparable_target = resolution.get("original_target")
    return {
        "id": str(case.get("id") or ""),
        "key": str(case.get("key") or ""),
        "loc": normalize_v3_context_text(case.get("loc")),
        "paragraph": normalize_v3_context_text(case.get("paragraph")),
        "anchor": normalize_v3_context_text(case.get("anchor")),
        "target": normalize_v3_context_text(comparable_target),
    }


def v3_context_mismatch_indexes(current_cases: list[dict[str, Any]], review_cases: list[dict[str, Any]]) -> list[int]:
    current_context = [v3_case_context_projection(case) for case in current_cases]
    review_context = [v3_case_context_projection(case) for case in review_cases]
    return [
        index
        for index, (current_case, review_case) in enumerate(zip(current_context, review_context))
        if current_case != review_case
    ]


def normalize_v3_context_text(value: Any) -> str:
    return " ".join(str(value or "").split())
