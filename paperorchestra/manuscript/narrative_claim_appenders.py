from __future__ import annotations

import json
import re
from typing import Any

from paperorchestra.manuscript.citations import canonical_citation_map
from paperorchestra.manuscript.narrative_claim_coverage import (
    _coverage_groups_for_benchmark,
    _coverage_groups_for_method,
    _first_key,
    _log_contains_result_claim,
)
from paperorchestra.manuscript.narrative_claim_record import _claim

LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?(?:\{[^}]*\})?")


def _append_method_claim(
    claims: list[dict[str, Any]],
    *,
    idx: int,
    state: Any,
    domain: Any,
    planning_text: str,
    author_source_text: str,
    template_planning_text: str,
    target_section: str,
) -> int:
    stripped_template_text = LATEX_COMMAND_RE.sub(" ", template_planning_text)
    template_terms = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", stripped_template_text)
    has_template_method_seed = domain.method_seed_re.search(stripped_template_text) and len(template_terms) >= 12
    if not domain.method_seed_re.search(author_source_text) and not has_template_method_seed:
        return idx
    excerpt = domain.method_excerpt_re.search(author_source_text) or domain.method_excerpt_re.search(template_planning_text)
    claims.append(
        _claim(
            idx=idx,
            text="The method description is limited to the construction, assumptions, and evidence stated for this paper.",
            claim_type="method",
            grounding="source_material",
            target_section=target_section,
            source_path=state.inputs.idea_path,
            excerpt=(excerpt.group(0) if excerpt else planning_text[:400]),
            coverage_groups=_coverage_groups_for_method(planning_text),
            risk="high",
        )
    )
    return idx + 1


def _append_proof_claim(
    claims: list[dict[str, Any]],
    *,
    idx: int,
    state: Any,
    domain: Any,
    planning_text: str,
    template_planning_text: str,
    target_section: str,
) -> int:
    if not domain.proof_seed_re.search(planning_text):
        return idx
    excerpt = domain.proof_excerpt_re.search(planning_text)
    claims.append(
        _claim(
            idx=idx,
            text="The analysis is grounded in the stated theorem, proof, model, and assumptions.",
            claim_type="proof",
            grounding="source_material",
            target_section=target_section,
            source_path=state.inputs.template_path,
            excerpt=(excerpt.group(0) if excerpt else template_planning_text[:400]),
            coverage_groups=[["analysis"], ["proof"], ["assumption"]],
            risk="high",
        )
    )
    return idx + 1


def _append_benchmark_claim(
    claims: list[dict[str, Any]],
    *,
    idx: int,
    state: Any,
    domain: Any,
    log_planning_text: str,
    target_section: str,
) -> int:
    if not domain.benchmark_seed_re.search(log_planning_text) or not _log_contains_result_claim(log_planning_text):
        return idx
    excerpt = domain.benchmark_excerpt_re.search(log_planning_text)
    claims.append(
        _claim(
            idx=idx,
            text="Performance comparisons are limited to the measurements, implementation profiles, and message-size settings reported in the experimental log.",
            claim_type="benchmark",
            grounding="experimental_log",
            target_section=target_section,
            source_path=state.inputs.experimental_log_path,
            excerpt=(excerpt.group(0) if excerpt else log_planning_text[:400]),
            coverage_groups=_coverage_groups_for_benchmark(log_planning_text),
            risk="high",
        )
    )
    return idx + 1


def _append_limitation_claim(
    claims: list[dict[str, Any]],
    *,
    idx: int,
    state: Any,
    planning_text: str,
    target_section: str,
) -> int:
    if not re.search(r"limitation|boundary|does not|not cover|assumption", planning_text, re.I):
        return idx
    excerpt = re.search(r".{0,120}(?:limitation|boundary|does not|not cover|assumption).{0,220}", planning_text, re.I | re.S)
    claims.append(
        _claim(
            idx=idx,
            text="The paper's conclusions remain within the stated limitations, assumptions, and claim boundaries.",
            claim_type="limitation",
            machine_obligation="Preserve the stated limitations, assumptions, and claim boundaries without broadening them.",
            grounding="human_boundary",
            target_section=target_section,
            source_path=state.inputs.idea_path,
            excerpt=(excerpt.group(0) if excerpt else planning_text[:400]),
            coverage_groups=[["limitation"], ["scope"], ["boundary"], ["assumption"]],
            risk="medium",
        )
    )
    return idx + 1


def _append_positioning_claim(
    claims: list[dict[str, Any]],
    *,
    idx: int,
    state: Any,
    citation_map: dict[str, Any],
    target_section: str,
) -> None:
    citation_key = _first_key(citation_map)
    if not citation_key or not target_section:
        return
    citation_entry = canonical_citation_map(citation_map).get(citation_key, {})
    if isinstance(citation_entry, dict):
        citation_entry = {key: value for key, value in citation_entry.items() if key != "provenance"}
    claims.append(
        _claim(
            idx=idx,
            text="The introduction and related work position the paper against verified background and baseline literature.",
            claim_type="positioning",
            machine_obligation="Use verified background literature for positioning and contrast.",
            grounding="verified_citation",
            target_section=target_section,
            source_path=state.artifacts.citation_map_json,
            excerpt=json.dumps(citation_entry, ensure_ascii=False)[:400],
            coverage_groups=[["related", "work"], ["background"]],
            required=False,
            citation_keys=[],
            risk="low",
        )
    )
