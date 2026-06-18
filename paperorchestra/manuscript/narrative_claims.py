from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.boundary import normalized_claim_projection
from paperorchestra.domains import detect_domain_for_text
from paperorchestra.manuscript.narrative_sections import NarrativeSectionTargets
from paperorchestra.manuscript.narrative_sources import _anchor, _planning_source_text, _salient_terms
from paperorchestra.manuscript.citations import canonical_citation_map

LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?(?:\{[^}]*\})?")


def _claim(
    *,
    idx: int,
    text: str,
    claim_type: str,
    grounding: str,
    target_section: str,
    source_path: str | Path | None,
    excerpt: str,
    coverage_groups: list[list[str]],
    required: bool = True,
    citation_keys: list[str] | None = None,
    risk: str = "medium",
    machine_obligation: str | None = None,
    authorial_claim: str | None = None,
    scope_note: str | None = None,
) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "id": f"claim-{idx:03d}",
        "text": authorial_claim or text,
        "claim_type": claim_type,
        "grounding": grounding,
        "source_refs": [str(source_path)] if source_path else [],
        "target_section": target_section,
        "citation_keys": citation_keys or [],
        "risk": risk,
        "required": required,
        "coverage_terms": sorted({term for group in coverage_groups for term in group}),
        "coverage_groups": coverage_groups,
        "evidence_anchors": [_anchor(source_path, excerpt)] if (required or excerpt) else [],
    }
    if machine_obligation:
        claim["machine_obligation"] = machine_obligation
    if authorial_claim:
        claim["authorial_claim"] = authorial_claim
    if scope_note:
        claim["scope_note"] = scope_note
    projection = normalized_claim_projection(claim)
    claim.setdefault("authorial_claim", projection["authorial_claim"])
    claim.setdefault("scope_note", projection["scope_note"])
    return claim


def _coverage_groups_for_method(source_text: str) -> list[list[str]]:
    groups: list[list[str]] = [["method"], ["construction"]]
    for term in _salient_terms(source_text, limit=4):
        if term not in {"method", "construction"}:
            groups.append([term])
    return groups


def _coverage_groups_for_benchmark(source_text: str) -> list[list[str]]:
    groups: list[list[str]] = [["benchmark", "measurement"], ["implementation", "profile"], ["message", "size"]]
    existing = {term for group in groups for term in group}
    for term in _salient_terms(_planning_source_text(source_text), limit=2):
        if term not in existing:
            groups.append([term])
    return groups


def _first_key(citation_map: dict[str, Any]) -> str | None:
    for key in canonical_citation_map(citation_map):
        if isinstance(key, str) and key.strip():
            return key
    return None


def _log_contains_result_claim(log_text: str) -> bool:
    if not log_text.strip():
        return False
    if re.search(r"\d+(?:\.\d+)\s*(?:x|×|%|ms|s|jobs/s|qps)?|\d+\s*(?:x|×|%|ms|s|jobs/s|qps)", log_text):
        return True
    result_words = (
        r"\b(report|reports|show|shows|improve|outperform|faster|slower|"
        r"accuracy|latency|throughput|runtime|speedup|ablation|result)\b"
    )
    return bool(
        re.search(
            result_words,
            log_text,
            re.I,
        )
    )


def build_claims(
    *,
    state: Any,
    planning_text: str,
    author_source_text: str,
    template_planning_text: str,
    log_planning_text: str,
    citation_map: dict[str, Any],
    targets: NarrativeSectionTargets,
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    idx = 1
    domain = detect_domain_for_text(planning_text)
    idx = _append_method_claim(
        claims,
        idx=idx,
        state=state,
        domain=domain,
        planning_text=planning_text,
        author_source_text=author_source_text,
        template_planning_text=template_planning_text,
        target_section=targets.method,
    )
    idx = _append_proof_claim(
        claims,
        idx=idx,
        state=state,
        domain=domain,
        planning_text=planning_text,
        template_planning_text=template_planning_text,
        target_section=targets.proof,
    )
    idx = _append_benchmark_claim(
        claims,
        idx=idx,
        state=state,
        domain=domain,
        log_planning_text=log_planning_text,
        target_section=targets.results,
    )
    idx = _append_limitation_claim(
        claims,
        idx=idx,
        state=state,
        planning_text=planning_text,
        target_section=targets.discussion,
    )
    _append_positioning_claim(
        claims,
        idx=idx,
        state=state,
        citation_map=citation_map,
        target_section=targets.positioning,
    )
    return claims


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
    template_terms = re.findall(
        r"[A-Za-z][A-Za-z0-9_-]{2,}",
        stripped_template_text,
    )
    has_template_method_seed = domain.method_seed_re.search(stripped_template_text) and len(template_terms) >= 12
    if not domain.method_seed_re.search(author_source_text) and not has_template_method_seed:
        return idx
    excerpt = domain.method_excerpt_re.search(author_source_text) or domain.method_excerpt_re.search(
        template_planning_text
    )
    claims.append(
        _claim(
            idx=idx,
            text=(
                "The method description is limited to the construction, assumptions, "
                "and evidence stated for this paper."
            ),
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
            text=(
                "Performance comparisons are limited to the measurements, implementation profiles, "
                "and message-size settings reported in the experimental log."
            ),
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
    excerpt = re.search(
        r".{0,120}(?:limitation|boundary|does not|not cover|assumption).{0,220}",
        planning_text,
        re.I | re.S,
    )
    claims.append(
        _claim(
            idx=idx,
            text="The paper's conclusions remain within the stated limitations, assumptions, and claim boundaries.",
            claim_type="limitation",
            machine_obligation=(
                "Preserve the stated limitations, assumptions, and claim boundaries without broadening them."
            ),
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
            text=(
                "The introduction and related work position the paper against verified background "
                "and baseline literature."
            ),
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
