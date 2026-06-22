from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from paperorchestra.core.errors import ContractError
from paperorchestra.core.io import read_json, write_text
from paperorchestra.core.models import utc_now_iso
from paperorchestra.core.session import artifact_path, load_session, save_session
from paperorchestra.engine.plan_gate import PlanGateResult, check_plan_gate, ensure_approved_plan
from paperorchestra.manuscript.narrative_artifacts import planning_artifact_status
from paperorchestra.manuscript.narrative_sources import file_sha256

PAPER_SKELETON_SCHEMA_VERSION = "paper-skeleton/1"
_PROVENANCE_RE = re.compile(
    r"<!--\s*paperorchestra:skeleton-provenance\s*\n(?P<payload>.*?)\n\s*-->",
    re.DOTALL,
)


def write_paper_skeleton(cwd: str | Path | None, *, gate: PlanGateResult | None = None) -> Path:
    """Write the derived paragraph-level paper skeleton.

    `paper-plan.md` remains the only author-approved source of truth.  The
    skeleton is a deterministic projection from that approved contract plus the
    generated outline/narrative/claim/citation planning artifacts.
    """

    gate = gate or ensure_approved_plan(cwd)
    require_skeleton_derivation_gate(gate)
    planning_status = planning_artifact_status(cwd)
    if planning_status["status"] != "pass":
        raise ContractError(
            "Fresh narrative planning artifacts are required before deriving paper-skeleton.md. "
            "Failing codes: " + ", ".join(planning_status["failing_codes"])
        )

    state = load_session(cwd)
    outline = _read_json_if_exists(state.artifacts.outline_json)
    payload = build_paper_skeleton_payload(
        gate=gate,
        outline=outline,
        narrative_plan=planning_status["payloads"].get("narrative_plan") or {},
        claim_map=planning_status["payloads"].get("claim_map") or {},
        citation_placement_plan=planning_status["payloads"].get("citation_placement_plan") or {},
        source_artifacts={
            "outline_json": state.artifacts.outline_json,
            "narrative_plan_json": state.artifacts.narrative_plan_json,
            "claim_map_json": state.artifacts.claim_map_json,
            "citation_placement_plan_json": state.artifacts.citation_placement_plan_json,
        },
    )
    validate_paper_skeleton_payload(payload)

    path = artifact_path(cwd, "paper-skeleton.md")
    write_text(path, render_paper_skeleton(payload))
    state = load_session(cwd)
    state.artifacts.paper_skeleton_md = str(path)
    state.notes.append("Derived paper-skeleton.md from the approved plan and fresh planning artifacts.")
    save_session(cwd, state)
    return path


def can_derive_paper_skeleton(gate: PlanGateResult) -> bool:
    return bool(gate.plan_path and gate.approval_state in {"approved_sidecar", "approved_hashed", "legacy_unhashed_approval"})


def require_skeleton_derivation_gate(gate: PlanGateResult) -> None:
    if can_derive_paper_skeleton(gate):
        return
    raise ContractError(
        "paper-skeleton.md can only be derived from an approved paper-plan.md. "
        "Explicit plan-gate bypass may draft without a skeleton, but it must not create one."
    )


def build_paper_skeleton_payload(
    *,
    gate: PlanGateResult,
    outline: dict[str, Any],
    narrative_plan: dict[str, Any],
    claim_map: dict[str, Any],
    citation_placement_plan: dict[str, Any],
    source_artifacts: dict[str, str | None],
) -> dict[str, Any]:
    claims = [claim for claim in claim_map.get("claims") or [] if isinstance(claim, dict)]
    claim_by_id = {str(claim.get("id") or ""): claim for claim in claims if str(claim.get("id") or "")}
    citations_by_claim = _citations_by_claim(citation_placement_plan)
    roles = _section_roles(narrative_plan, outline)
    sections = [
        _section_payload(
            role=role,
            claims=[claim for claim in claims if claim.get("target_section") == role["section_title"]],
            citations_by_claim=citations_by_claim,
        )
        for role in roles
    ]
    return {
        "schema_version": PAPER_SKELETON_SCHEMA_VERSION,
        "derived_at": utc_now_iso(),
        "authoritative": False,
        "authority_note": "Derived projection only; paper-plan.md remains the sole author-approved contract.",
        "plan": {
            "path": gate.plan_path,
            "approval_state": gate.approval_state,
            "approval_revision": gate.approval_revision,
            "contract_sha256": gate.contract_sha256,
            "warning": gate.warning,
        },
        "source_artifacts": {name: _artifact_ref(path) for name, path in source_artifacts.items()},
        "invariants": {
            "no_new_major_claims": True,
            "claim_refs_must_exist_in_claim_map": True,
            "citation_claim_refs_must_exist_in_claim_map": True,
            "paragraphs_must_not_exceed_claim_map_strength": True,
            "stale_plan_or_source_hash_blocks_use": True,
        },
        "claim_registry": {
            claim_id: {
                "target_section": str(claim.get("target_section") or ""),
                "claim_type": claim.get("claim_type"),
                "grounding": claim.get("grounding"),
                "maximum_strength": _maximum_strength(claim),
                "authorial_claim": claim.get("authorial_claim") or claim.get("text") or "",
                "scope_note": claim.get("scope_note") or "",
                "source_refs": claim.get("source_refs") or [],
            }
            for claim_id, claim in claim_by_id.items()
        },
        "source_claim_refs": {
            "citation_placement_plan": sorted(citations_by_claim),
            "narrative_plan": sorted(_narrative_claim_refs(narrative_plan)),
        },
        "sections": sections,
    }


def validate_paper_skeleton_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != PAPER_SKELETON_SCHEMA_VERSION:
        raise ContractError("paper-skeleton.md has an unsupported schema_version.")
    claim_registry = payload.get("claim_registry")
    if not isinstance(claim_registry, dict):
        raise ContractError("paper-skeleton.md is missing claim_registry.")
    claim_ids = set(str(key) for key in claim_registry)
    source_claim_refs = payload.get("source_claim_refs") or {}
    if isinstance(source_claim_refs, dict):
        for source, refs in source_claim_refs.items():
            for claim_id in refs or []:
                if str(claim_id) not in claim_ids:
                    raise ContractError(f"paper-skeleton.md {source} references unknown claim id `{claim_id}`.")
    for section in payload.get("sections") or []:
        if not isinstance(section, dict):
            raise ContractError("paper-skeleton.md has an invalid section entry.")
        for paragraph in section.get("paragraphs") or []:
            _validate_paragraph_claim_refs(paragraph, claim_ids)
    for section in payload.get("sections") or []:
        for paragraph in section.get("paragraphs") or []:
            for claim_id in paragraph.get("claim_refs") or []:
                expected = claim_registry[str(claim_id)]
                if paragraph.get("claim_summary") != expected.get("authorial_claim"):
                    raise ContractError(
                        f"paper-skeleton.md paragraph {paragraph.get('paragraph_id')} changes claim text for {claim_id}."
                    )


def paper_skeleton_status(cwd: str | Path | None) -> dict[str, Any]:
    try:
        state = load_session(cwd)
    except Exception as exc:
        return {"status": "not_applicable", "reason": f"session_unavailable: {exc}"}

    path = Path(state.artifacts.paper_skeleton_md) if state.artifacts.paper_skeleton_md else artifact_path(cwd, "paper-skeleton.md")
    if not path.exists():
        return {"status": "missing", "path": str(path), "reason": "paper_skeleton_missing"}
    try:
        payload = read_paper_skeleton_payload(path)
        validate_paper_skeleton_payload(payload)
    except Exception as exc:
        return {"status": "invalid", "path": str(path), "reason": "paper_skeleton_invalid", "detail": str(exc)}

    gate = check_plan_gate(cwd)
    if not gate.allowed:
        return {
            "status": "stale",
            "path": str(path),
            "reason": "approved_plan_unavailable",
            "plan_gate": gate.to_dict(),
        }
    recorded_hash = (payload.get("plan") or {}).get("contract_sha256")
    if recorded_hash != gate.contract_sha256:
        return {
            "status": "stale",
            "path": str(path),
            "reason": "plan_contract_hash_mismatch",
            "recorded_contract_sha256": recorded_hash,
            "current_contract_sha256": gate.contract_sha256,
        }

    source_mismatches = _source_artifact_mismatches(payload.get("source_artifacts") or {})
    if source_mismatches:
        return {"status": "stale", "path": str(path), "reason": "source_artifact_hash_mismatch", "mismatches": source_mismatches}

    planning_status = planning_artifact_status(cwd)
    if planning_status["status"] != "pass":
        return {
            "status": "stale",
            "path": str(path),
            "reason": "planning_artifacts_stale",
            "failing_codes": planning_status["failing_codes"],
        }

    return {
        "status": "pass",
        "path": str(path),
        "plan_contract_sha256": gate.contract_sha256,
        "section_count": len(payload.get("sections") or []),
    }


def read_paper_skeleton_payload(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    match = _PROVENANCE_RE.search(text)
    if not match:
        raise ContractError("paper-skeleton.md is missing its machine-readable provenance block.")
    return json.loads(match.group("payload"))


def render_paper_skeleton(payload: dict[str, Any]) -> str:
    provenance = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    lines = [
        "# PaperOrchestra Paper Skeleton",
        "",
        "> Derived projection only. `paper-plan.md` remains the only author-approved contract.",
        "",
        "<!-- paperorchestra:skeleton-provenance",
        provenance,
        "-->",
        "",
        "## Provenance",
        "",
        f"- Plan: `{(payload.get('plan') or {}).get('path')}`",
        f"- Contract SHA-256: `{(payload.get('plan') or {}).get('contract_sha256')}`",
        "- Approval source: `paper-plan.md`; this skeleton is not a second approval source.",
        "",
        "## Paragraph move sequence",
        "",
    ]
    for section in payload.get("sections") or []:
        lines.extend(_render_section(section))
    return "\n".join(lines).rstrip() + "\n"


def _render_section(section: dict[str, Any]) -> list[str]:
    title = section.get("section_title") or "Untitled"
    lines = [
        f"### {title}",
        "",
        f"- Rhetorical job: {section.get('rhetorical_job') or 'Use the approved plan and evidence without broadening claims.'}",
        f"- Completion check: {section.get('completion_check') or 'All claim refs are covered within their boundaries.'}",
        "",
    ]
    for paragraph in section.get("paragraphs") or []:
        lines.extend(
            [
                f"{paragraph.get('paragraph_id')}. {paragraph.get('move')}",
                f"   - claim refs: {', '.join(paragraph.get('claim_refs') or []) or 'none'}",
                f"   - evidence refs: {', '.join(paragraph.get('evidence_refs') or []) or 'none'}",
                f"   - citation refs: {', '.join(paragraph.get('citation_refs') or []) or 'none'}",
                f"   - maximum strength: {paragraph.get('maximum_strength')}",
                "",
            ]
        )
    return lines


def _section_payload(
    *,
    role: dict[str, Any],
    claims: list[dict[str, Any]],
    citations_by_claim: dict[str, list[str]],
) -> dict[str, Any]:
    title = str(role.get("section_title") or "Untitled")
    paragraphs = [
        _claim_paragraph(title=title, claim=claim, citations_by_claim=citations_by_claim, order=index + 1)
        for index, claim in enumerate(claims)
    ]
    if not paragraphs:
        paragraphs.append(
            {
                "paragraph_id": f"{_section_slug(title)}-P001",
                "move": "Execute the section role without introducing a new thesis-critical claim.",
                "intent": str(role.get("role") or "Provide connective scholarly prose."),
                "claim_refs": [],
                "evidence_refs": [],
                "citation_refs": [],
                "prohibited_moves": list(role.get("must_not_claim") or []),
                "completion_check": "Section role is satisfied without adding unregistered major claims.",
                "maximum_strength": "no thesis-critical claim without plan revision",
            }
        )
    return {
        "section_title": title,
        "rhetorical_job": role.get("role") or "Use the approved plan and evidence without broadening claims.",
        "claim_refs": [str(claim.get("id")) for claim in claims if claim.get("id")],
        "prohibited_moves": list(role.get("must_not_claim") or []),
        "completion_check": "Covers listed claim refs and preserves their scope notes.",
        "paragraphs": paragraphs,
    }


def _claim_paragraph(
    *,
    title: str,
    claim: dict[str, Any],
    citations_by_claim: dict[str, list[str]],
    order: int,
) -> dict[str, Any]:
    claim_id = str(claim.get("id") or "")
    scope_note = str(claim.get("scope_note") or "").strip()
    prohibited = [
        "Do not introduce a new major claim not listed in claim_map.json.",
        "Do not strengthen comparative, causal, novelty, or generalization wording beyond the claim_map entry.",
    ]
    if scope_note:
        prohibited.append(f"Do not omit this boundary: {scope_note}")
    return {
        "paragraph_id": f"{_section_slug(title)}-P{order:03d}",
        "move": f"Cover {claim_id} as a bounded authorial claim.",
        "intent": "Make the reader accept the registered claim only at its approved strength.",
        "claim_refs": [claim_id],
        "claim_summary": claim.get("authorial_claim") or claim.get("text") or "",
        "evidence_refs": [str(ref) for ref in claim.get("source_refs") or []],
        "citation_refs": citations_by_claim.get(claim_id, []),
        "prohibited_moves": prohibited,
        "completion_check": "Claim is stated, evidence/citation refs are connected, and the boundary is explicit.",
        "maximum_strength": _maximum_strength(claim),
    }


def _section_roles(narrative_plan: dict[str, Any], outline: dict[str, Any]) -> list[dict[str, Any]]:
    roles = narrative_plan.get("section_roles")
    if isinstance(roles, list) and roles:
        return [role for role in roles if isinstance(role, dict)]
    return [
        {"section_title": item.get("section_title"), "role": "Draft this planned section within approved claim boundaries."}
        for item in outline.get("section_plan") or []
        if isinstance(item, dict) and item.get("section_title")
    ]


def _citations_by_claim(citation_placement_plan: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for placement in citation_placement_plan.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        claim_id = str(placement.get("claim_id") or "")
        if not claim_id:
            continue
        result.setdefault(claim_id, [])
        for key in placement.get("citation_keys") or []:
            key = str(key).strip()
            if key and key not in result[claim_id]:
                result[claim_id].append(key)
    return result


def _narrative_claim_refs(narrative_plan: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for role in narrative_plan.get("section_roles") or []:
        if not isinstance(role, dict):
            continue
        for requirement in role.get("coverage_requirements") or []:
            if isinstance(requirement, dict) and requirement.get("claim_id"):
                refs.add(str(requirement["claim_id"]))
    for beat in narrative_plan.get("story_beats") or []:
        if isinstance(beat, dict) and beat.get("claim_id"):
            refs.add(str(beat["claim_id"]))
    return refs


def _validate_paragraph_claim_refs(paragraph: dict[str, Any], claim_ids: set[str]) -> None:
    if not isinstance(paragraph, dict):
        raise ContractError("paper-skeleton.md has an invalid paragraph entry.")
    for claim_id in paragraph.get("claim_refs") or []:
        if str(claim_id) not in claim_ids:
            raise ContractError(f"paper-skeleton.md references unknown claim id `{claim_id}`.")


def _source_artifact_mismatches(recorded: dict[str, Any]) -> list[dict[str, str | None]]:
    mismatches: list[dict[str, str | None]] = []
    for name, ref in recorded.items():
        if not isinstance(ref, dict):
            continue
        path = ref.get("path")
        current = file_sha256(path)
        if current != ref.get("sha256"):
            mismatches.append(
                {
                    "artifact": name,
                    "path": str(path) if path else None,
                    "recorded_sha256": ref.get("sha256"),
                    "current_sha256": current,
                }
            )
    return mismatches


def _artifact_ref(path: str | Path | None) -> dict[str, Any]:
    resolved = Path(path).resolve() if path else None
    return {
        "path": str(resolved) if resolved else None,
        "exists": bool(resolved and resolved.exists()),
        "sha256": file_sha256(resolved) if resolved else None,
    }


def _read_json_if_exists(path: str | Path | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _maximum_strength(claim: dict[str, Any]) -> str:
    claim_type = str(claim.get("claim_type") or "claim")
    grounding = str(claim.get("grounding") or "unknown-grounding")
    risk = str(claim.get("risk") or "medium")
    return f"no stronger than claim_map.{claim_type} supported by {grounding} (risk={risk})"


def _section_slug(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title.strip().lower()).strip("-")
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
    return f"{slug or 'section'}-{digest}"


__all__ = [
    "PAPER_SKELETON_SCHEMA_VERSION",
    "build_paper_skeleton_payload",
    "can_derive_paper_skeleton",
    "paper_skeleton_status",
    "read_paper_skeleton_payload",
    "render_paper_skeleton",
    "require_skeleton_derivation_gate",
    "validate_paper_skeleton_payload",
    "write_paper_skeleton",
]
