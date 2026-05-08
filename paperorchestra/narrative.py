from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .boundary import is_material_packet_control_section_title, is_material_packet_section_title, normalized_claim_projection
from .domains import detect_domain_for_text, get_domain
from .io_utils import read_json, write_json
from .session import artifact_path, load_session, save_session

NARRATIVE_PLAN_SCHEMA_VERSION = "narrative-plan/1"
CLAIM_MAP_SCHEMA_VERSION = "claim-map/1"
CITATION_PLACEMENT_PLAN_SCHEMA_VERSION = "citation-placement-plan/1"


def _plain_section_title(title: str) -> str:
    match = re.fullmatch(r"\\(?:sub)*section\*?\{(.+)\}", title.strip(), flags=re.DOTALL)
    return match.group(1).strip() if match else title.strip()


def file_sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    return "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()


def _read_text(path: str | Path | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def planning_source_hashes(cwd: str | Path | None) -> dict[str, str | None]:
    state = load_session(cwd)
    return {
        "outline_json": file_sha256(state.artifacts.outline_json),
        "citation_map_json": file_sha256(state.artifacts.citation_map_json),
        "references_bib": file_sha256(state.artifacts.references_bib),
        "idea_md": file_sha256(state.inputs.idea_path),
        "experimental_log_md": file_sha256(state.inputs.experimental_log_path),
        "template_tex": file_sha256(state.inputs.template_path),
    }


def _line_span(text: str, needle: str) -> tuple[int | None, int | None]:
    if not needle:
        return None, None
    idx = text.lower().find(needle.lower())
    if idx < 0:
        return None, None
    return text.count("\n", 0, idx) + 1, text.count("\n", 0, idx + len(needle)) + 1


def _anchor(path: str | Path | None, excerpt: str) -> dict[str, Any]:
    text = _read_text(path)
    line_start, line_end = _line_span(text, excerpt[:80])
    return {
        "source_ref": str(path) if path else None,
        "source_sha256": file_sha256(path),
        "evidence_excerpt": excerpt[:500],
        "line_start": line_start,
        "line_end": line_end,
    }


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
        "evidence_anchors": [_anchor(source_path, excerpt)] if required else [],
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
    groups: list[list[str]] = [["benchmark"], ["measurement"]]
    for term in _salient_terms(source_text, limit=3):
        if term not in {"benchmark", "measurement"}:
            groups.append([term])
    return groups


def _salient_terms(text: str, *, limit: int = 5) -> list[str]:
    stop = {
        "the", "and", "that", "with", "from", "this", "paper", "section", "method", "result", "results",
        "using", "used", "uses", "into", "for", "are", "was", "were", "our", "their", "stated",
        "evidence", "assumptions", "construction", "benchmark", "measurement",
    }
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+_.-]{2,}|\d+(?:\.\d+)?\s*(?:x|×|%|ms|s|jobs/s|qps)", text):
        term = token.lower().strip(" .,:;()[]{}")
        if term in stop or len(term) < 3 or term in terms:
            continue
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def _section_titles(outline: dict[str, Any], template_text: str) -> list[str]:
    titles: list[str] = []
    saw_material_packet_control_section = False
    for item in outline.get("section_plan") or []:
        if isinstance(item, dict) and isinstance(item.get("section_title"), str):
            title = _plain_section_title(item["section_title"])
            if is_material_packet_control_section_title(title):
                saw_material_packet_control_section = True
            if not is_material_packet_section_title(title):
                titles.append(title)
    if saw_material_packet_control_section and not any(title.strip().lower() == "discussion" for title in titles):
        titles.append("Discussion")
    if titles:
        return titles
    template_titles = []
    for match in re.finditer(r"\\section\*?\{([^}]+)\}", template_text):
        title = match.group(1).strip()
        if not is_material_packet_section_title(title):
            template_titles.append(title)
    return template_titles


def _first_key(citation_map: dict[str, Any]) -> str | None:
    for key in citation_map:
        if isinstance(key, str) and key.strip():
            return key
    return None


def _log_contains_result_claim(log_text: str) -> bool:
    if not log_text.strip():
        return False
    if re.search(r"\d+(?:\.\d+)\s*(?:x|×|%|ms|s|jobs/s|qps)?|\d+\s*(?:x|×|%|ms|s|jobs/s|qps)", log_text):
        return True
    return bool(re.search(r"\b(report|reports|show|shows|improve|outperform|faster|slower|accuracy|latency|throughput|runtime|speedup|ablation|result)\b", log_text, re.I))


def build_planning_payloads(cwd: str | Path | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = load_session(cwd)
    outline = read_json(state.artifacts.outline_json) if state.artifacts.outline_json else {"section_plan": []}
    citation_map = read_json(state.artifacts.citation_map_json) if state.artifacts.citation_map_json else {}
    idea_text = _read_text(state.inputs.idea_path)
    log_text = _read_text(state.inputs.experimental_log_path)
    template_text = _read_text(state.inputs.template_path)
    source_text = "\n".join([idea_text, log_text, template_text])
    author_source_text = "\n".join([idea_text, log_text])
    hashes = planning_source_hashes(cwd)
    sections = _section_titles(outline, template_text) or [
        "Introduction",
        "Related Work",
        "Method",
        "Experiments",
        "Discussion",
        "Conclusion",
    ]
    method_section = next((s for s in sections if re.search(r"method|approach|construction", s, re.I)), "Method")
    proof_section = next((s for s in sections if re.search(r"security|proof|analysis", s, re.I)), method_section)
    results_section = next((s for s in sections if re.search(r"experiment|result|benchmark|evaluation", s, re.I)), "Experiments")
    discussion_section = next((s for s in sections if re.search(r"discussion|limitation", s, re.I)), "Discussion")
    claims: list[dict[str, Any]] = []
    idx = 1
    domain = detect_domain_for_text(source_text)
    if domain.method_seed_re.search(author_source_text) or (
        domain.method_seed_re.search(template_text) and len(re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})?", " ", template_text))) >= 12
    ):
        excerpt = domain.method_excerpt_re.search(author_source_text) or domain.method_excerpt_re.search(template_text)
        claims.append(
            _claim(
                idx=idx,
                text="The method description is limited to the construction, assumptions, and evidence stated for this paper.",
                claim_type="method",
                grounding="source_material",
                target_section=method_section,
                source_path=state.inputs.idea_path,
                excerpt=(excerpt.group(0) if excerpt else source_text[:400]),
                coverage_groups=_coverage_groups_for_method(source_text),
                risk="high",
            )
        )
        idx += 1
    if domain.proof_seed_re.search(source_text):
        excerpt = domain.proof_excerpt_re.search(source_text)
        claims.append(
            _claim(
                idx=idx,
                text="The analysis is grounded in the stated theorem, proof, model, and assumptions.",
                claim_type="proof",
                grounding="source_material",
                target_section=proof_section,
                source_path=state.inputs.template_path,
                excerpt=(excerpt.group(0) if excerpt else template_text[:400]),
                coverage_groups=[["analysis"], ["proof"], ["assumption"]],
                risk="high",
            )
        )
        idx += 1
    if domain.benchmark_seed_re.search(log_text) and _log_contains_result_claim(log_text):
        excerpt = domain.benchmark_excerpt_re.search(log_text)
        claims.append(
            _claim(
                idx=idx,
                text="Performance comparisons are limited to the measurements, implementation profiles, and message-size settings reported in the experimental log.",
                claim_type="benchmark",
                grounding="experimental_log",
                target_section=results_section,
                source_path=state.inputs.experimental_log_path,
                excerpt=(excerpt.group(0) if excerpt else log_text[:400]),
                coverage_groups=_coverage_groups_for_benchmark(source_text),
                risk="high",
            )
        )
        idx += 1
    if re.search(r"limitation|boundary|does not|not cover|assumption", source_text, re.I):
        excerpt = re.search(r".{0,120}(?:limitation|boundary|does not|not cover|assumption).{0,220}", source_text, re.I | re.S)
        claims.append(
            _claim(
                idx=idx,
                text="The paper's conclusions remain within the stated limitations, assumptions, and claim boundaries.",
                claim_type="limitation",
                machine_obligation="Preserve the stated limitations, assumptions, and claim boundaries without broadening them.",
                grounding="human_boundary",
                target_section=discussion_section,
                source_path=state.inputs.idea_path,
                excerpt=(excerpt.group(0) if excerpt else source_text[:400]),
                coverage_groups=[["limitation"], ["scope"], ["boundary"], ["assumption"]],
                risk="medium",
            )
        )
        idx += 1
    citation_key = _first_key(citation_map if isinstance(citation_map, dict) else {})
    positioning_section = next((s for s in sections if re.search(r"related|introduction", s, re.I)), "")
    if citation_key and positioning_section:
        claims.append(
            _claim(
                idx=idx,
                text="The introduction and related work position the paper against verified background and baseline literature.",
                claim_type="positioning",
                machine_obligation="Use verified background literature for positioning and contrast.",
                grounding="verified_citation",
                target_section=positioning_section,
                source_path=state.artifacts.citation_map_json,
                excerpt=json.dumps(citation_map.get(citation_key, {}), ensure_ascii=False)[:400],
                coverage_groups=[["related", "work"], ["background"]],
                required=False,
                citation_keys=[],
                risk="low",
            )
        )
        idx += 1
    projections = [normalized_claim_projection(claim) for claim in claims]
    projections_by_id = {projection["id"]: projection for projection in projections}
    narrative = {
        "schema_version": NARRATIVE_PLAN_SCHEMA_VERSION,
        "source_hashes": hashes,
        "thesis": "Build a coherent scholarly draft that preserves the paper's method, proof, benchmark, and limitation scope while using verified references for positioning.",
        "contribution_boundary": [
            "Keep method, proof, benchmark, and limitation claims within the stated assumptions and evidence.",
            "Use external citations for background, standards, baselines, and contrast rather than unsupported core results.",
        ],
        "section_roles": [
            {
                "section_title": title,
                "role": "Develop this section from the technical evidence, stated assumptions, and assigned citations without adding unsupported claims.",
                "must_cover": [
                    projections_by_id[str(claim.get("id") or "")]["authorial_claim"]
                    for claim in claims
                    if claim.get("target_section") == title and claim.get("required") and str(claim.get("id") or "") in projections_by_id
                ],
                "coverage_requirements": [
                    {
                        "claim_id": projection["id"],
                        "authorial_claim": projection["authorial_claim"],
                        "coverage_terms": projection["coverage_terms"],
                        "coverage_groups": projection["coverage_groups"],
                    }
                    for projection in projections
                    if projection.get("target_section") == title and projection.get("required")
                ],
                "must_not_claim": ["submission ready", "camera-ready", "unqualified automatic acceptance", "human review is unnecessary", "guaranteed scientific correctness"],
            }
            for title in sections
        ],
        "story_beats": [
            {
                "order": i + 1,
                "beat": projection["authorial_claim"],
                "target_section": projection["target_section"],
                "evidence_source": projection["grounding"],
                "coverage_terms": projection["coverage_terms"],
                "coverage_groups": projection["coverage_groups"],
            }
            for i, projection in enumerate(projections)
            if projection.get("required")
        ],
    }
    claim_map = {
        "schema_version": CLAIM_MAP_SCHEMA_VERSION,
        "source_hashes": hashes,
        "claims": claims,
    }
    placements = []
    for claim in claims:
        if claim.get("citation_keys"):
            placements.append(
                {
                    "claim_id": claim["id"],
                    "target_section": claim["target_section"],
                    "citation_keys": claim["citation_keys"],
                    "support_role": "background" if claim["claim_type"] == "positioning" else "contrast",
                    "placement_rule": "same_sentence_or_adjacent",
                }
            )
    citation_plan = {
        "schema_version": CITATION_PLACEMENT_PLAN_SCHEMA_VERSION,
        "source_hashes": hashes,
        "placements": placements,
    }
    return narrative, claim_map, citation_plan


def write_planning_artifacts(cwd: str | Path | None) -> dict[str, Path]:
    narrative, claim_map, citation_plan = build_planning_payloads(cwd)
    narrative_path = artifact_path(cwd, "narrative_plan.json")
    claim_path = artifact_path(cwd, "claim_map.json")
    citation_path = artifact_path(cwd, "citation_placement_plan.json")
    write_json(narrative_path, narrative)
    write_json(claim_path, claim_map)
    write_json(citation_path, citation_plan)
    state = load_session(cwd)
    state.artifacts.narrative_plan_json = str(narrative_path)
    state.artifacts.claim_map_json = str(claim_path)
    state.artifacts.citation_placement_plan_json = str(citation_path)
    state.notes.append("Narrative/claim/citation placement planning artifacts recorded.")
    save_session(cwd, state)
    return {
        "narrative_plan": narrative_path,
        "claim_map": claim_path,
        "citation_placement_plan": citation_path,
    }


def planning_artifact_status(cwd: str | Path | None) -> dict[str, Any]:
    state = load_session(cwd)
    current_hashes = planning_source_hashes(cwd)
    artifacts = {
        "narrative_plan": state.artifacts.narrative_plan_json,
        "claim_map": state.artifacts.claim_map_json,
        "citation_placement_plan": state.artifacts.citation_placement_plan_json,
    }
    missing: list[str] = []
    stale: list[str] = []
    payloads: dict[str, dict[str, Any]] = {}
    for name, path in artifacts.items():
        if not path or not Path(path).exists():
            missing.append(f"{name}_missing")
            continue
        payload = read_json(path)
        payloads[name] = payload
        if payload.get("source_hashes") != current_hashes:
            stale.append(f"{name}_stale")
    return {
        "status": "fail" if missing or stale else "pass",
        "failing_codes": missing + stale,
        "source_hashes": current_hashes,
        "artifacts": artifacts,
        "payloads": payloads,
    }


def require_fresh_planning_artifacts(cwd: str | Path | None) -> None:
    status = planning_artifact_status(cwd)
    if status["status"] != "pass":
        raise RuntimeError(
            "Fresh narrative planning artifacts are required before writing. "
            "Run `paperorchestra plan-narrative`. Failing codes: "
            + ", ".join(status["failing_codes"])
        )
