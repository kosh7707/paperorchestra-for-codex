from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .orchestrator import inspect_state as orchestrator_inspect_state

FIRST_USER_GUIDE_SCHEMA_VERSION = "first-user-guide/1"
FIRST_USER_INTENTS = {"auto", "setup", "how_to_use", "start", "write_now"}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _redacted_material_root(path: str | Path) -> str:
    return f"redacted-material-root:{_sha256_text(str(Path(path).expanduser().resolve()))[:12]}"


def _normalize_intent(intent: str | None) -> str:
    value = (intent or "auto").strip()
    if value not in FIRST_USER_INTENTS:
        raise ValueError(f"unsupported first-use intent: {value}")
    return "how_to_use" if value == "auto" else value


def _mcp_status(value: bool | str | None) -> str:
    if value is True or value == "yes":
        return "attached"
    if value is False or value == "no":
        return "registered_only"
    return "unknown"


def _scorecard_from_state(state_payload: dict[str, Any], *, mcp_attached: bool | str | None) -> dict[str, str]:
    five_axis = state_payload.get("five_axis_status") if isinstance(state_payload.get("five_axis_status"), dict) else {}
    material_axis = str(five_axis.get("materials", "missing"))
    material = "ok" if material_axis == "ready" else material_axis
    evidence_axis = str(state_payload.get("facets", {}).get("evidence", "missing")) if isinstance(state_payload.get("facets"), dict) else "missing"
    evidence = {
        "supported": "ok",
        "research_needed": "needs_research",
        "durable_research_needed": "needs_research",
        "blocked": "insufficient",
        "missing": "missing",
    }.get(evidence_axis, evidence_axis)
    citations = str(five_axis.get("citations", "unknown"))
    figures = str(five_axis.get("figures", "unknown"))
    return {
        "material": material,
        "evidence": evidence,
        "citations": citations,
        "figures": figures,
        "mcp": _mcp_status(mcp_attached),
    }


def _safe_state(cwd: str | Path | None, *, material: str | Path | None) -> dict[str, Any]:
    state = orchestrator_inspect_state(cwd, material_path=material)
    payload = state.to_public_dict()
    payload.pop("cwd", None)
    return payload


def _needs_material(scorecard: dict[str, str]) -> bool:
    return scorecard.get("material") in {"missing", "insufficient", "inventoried_insufficient"}


def _base_next_action(action_type: str, *, surface: str, reason: str) -> dict[str, str]:
    return {"action_type": action_type, "surface": surface, "reason": reason}


def _workflow_surface(scorecard: dict[str, str]) -> str:
    return "mcp" if scorecard.get("mcp") == "attached" else "cli"


def _next_actions_for(intent: str, *, scorecard: dict[str, str], material_ref: str | None) -> list[dict[str, str]]:
    workflow_surface = _workflow_surface(scorecard)
    if intent == "setup":
        return [
            _base_next_action("setup_environment", surface="cli", reason="Create/reuse venv, install package, and run doctor/environment checks."),
            _base_next_action("register_mcp", surface="cli", reason="Register PaperOrchestra MCP and Skill, then distinguish registration from active attachment."),
            _base_next_action("smoke_mcp", surface="cli", reason="Run raw MCP smoke plus active Codex attach smoke after restart."),
            _base_next_action("restart_codex", surface="operator", reason="Active MCP tools are injected only into a new Codex session."),
        ]
    if intent == "write_now" and _needs_material(scorecard):
        return [
            _base_next_action("provide_material", surface="operator", reason="A paper draft needs private source material; the engine cannot invent claims/results."),
            _base_next_action("start_intake", surface=workflow_surface, reason="Collect missing author-owned intent and material references through guided intake."),
            _base_next_action("safe_mock_demo", surface="cli", reason="If you only want a smoke test, run the mock demo instead of a factual draft."),
        ]
    if _needs_material(scorecard):
        return [
            _base_next_action("inspect_state", surface=workflow_surface, reason="Inspect current session/material state before choosing a workflow."),
            _base_next_action("provide_material", surface="operator", reason="Point PaperOrchestra at the material folder or existing manuscript/artifact repo."),
            _base_next_action("start_intake", surface=workflow_surface, reason="Use guided intake when material is not yet organized."),
        ]
    return [
        _base_next_action("orchestrate", surface=workflow_surface, reason="Run the bounded orchestrator from the inspected material state."),
        _base_next_action("quality_gate", surface=workflow_surface, reason="Use hard gates and scorecards before any human-finalization claim."),
        _base_next_action("export_results", surface=workflow_surface, reason="Export only after draft, compile, and quality gates have evidence."),
    ]


def _author_questions_for(intent: str, *, scorecard: dict[str, str]) -> list[dict[str, str]]:
    if scorecard.get("material") == "missing":
        return [
            {
                "question": "어느 폴더나 파일에 논문 재료가 있나요?",
                "why_user_owned": "Private source material location is author-owned and cannot be discovered safely without a path.",
            }
        ]
    if intent == "write_now" and scorecard.get("material") == "insufficient":
        return [
            {
                "question": "추가 실험 로그, 아이디어 설명, 원고, 또는 가이드라인 중 무엇을 제공할 수 있나요?",
                "why_user_owned": "The engine can organize supplied material, but it cannot invent missing evidence.",
            }
        ]
    return []


def _status_for(intent: str, *, scorecard: dict[str, str]) -> str:
    if intent == "setup":
        return "needs_setup" if scorecard.get("mcp") != "attached" else "ready"
    if intent == "write_now" and _needs_material(scorecard):
        return "blocked"
    if _needs_material(scorecard):
        return "needs_material"
    if scorecard.get("mcp") == "registered_only":
        return "mcp_fallback"
    return "ready"


def _summary_for(intent: str, *, status: str, scorecard: dict[str, str]) -> str:
    if intent == "setup":
        return "Set up the environment, register MCP/Skill, run smoke checks, then restart Codex to verify active attachment."
    if intent == "write_now" and status == "blocked":
        return "Drafting is blocked: material is insufficient, so writing now would require invented claims, citations, or results."
    if status == "needs_material":
        return "PaperOrchestra can guide the process, but it needs a material folder, existing manuscript, or guided intake first."
    if status == "mcp_fallback":
        return "MCP appears registered but not attached; use CLI fallback until a restarted Codex session exposes native tools."
    return "Proceed with the bounded orchestrator path unless interrupted; machine-solvable checks run before author-judgment questions."


def build_first_user_guide(
    cwd: str | Path | None = None,
    *,
    intent: str | None = "auto",
    material: str | Path | None = None,
    mcp_attached: bool | str | None = None,
) -> dict[str, Any]:
    normalized_intent = _normalize_intent(intent)
    state_payload = _safe_state(cwd, material=material)
    scorecard = _scorecard_from_state(state_payload, mcp_attached=mcp_attached)
    status = _status_for(normalized_intent, scorecard=scorecard)
    material_ref = _redacted_material_root(material) if material else None
    refusal = {
        "refused": bool(normalized_intent == "write_now" and status == "blocked"),
        "reason": "",
    }
    if refusal["refused"]:
        refusal["reason"] = "insufficient material; drafting would require invented claims/results/citations"

    return {
        "schema_version": FIRST_USER_GUIDE_SCHEMA_VERSION,
        "intent": normalized_intent,
        "status": status,
        "scorecard": scorecard,
        "summary": _summary_for(normalized_intent, status=status, scorecard=scorecard),
        "material_ref": material_ref,
        "state": {
            "readiness": state_payload.get("readiness"),
            "five_axis_status": state_payload.get("five_axis_status"),
            "blocking_reasons": state_payload.get("blocking_reasons", []),
            "next_actions": state_payload.get("next_actions", []),
        },
        "next_actions": _next_actions_for(normalized_intent, scorecard=scorecard, material_ref=material_ref),
        "author_questions": _author_questions_for(normalized_intent, scorecard=scorecard),
        "refusal": refusal,
        "notes": [
            "codex mcp list proves registration, not active attachment.",
            "Raw MCP smoke proves server health; native mcp__paperorchestra__ tools prove active attachment.",
            "This guide is read-only and does not run live search, drafting, compile, or OMX workflows.",
        ],
        "private_safe_summary": True,
    }


def render_first_user_guide_summary(payload: dict[str, Any]) -> str:
    scorecard = payload.get("scorecard") if isinstance(payload.get("scorecard"), dict) else {}
    lines = [
        "PaperOrchestra first-use guide",
        f"Intent: {payload.get('intent')}",
        f"Status: {payload.get('status')}",
        "",
        "Scorecard:",
    ]
    for axis in ["material", "evidence", "citations", "figures", "mcp"]:
        lines.append(f"  {axis}: {scorecard.get(axis, 'unknown')}")
    lines.extend(["", f"Summary: {payload.get('summary', '')}", "", "Next:"])
    for action in payload.get("next_actions", []):
        if not isinstance(action, dict):
            continue
        lines.append(f"  - {action.get('action_type')} ({action.get('surface')}): {action.get('reason')}")
    refusal = payload.get("refusal") if isinstance(payload.get("refusal"), dict) else {}
    if refusal.get("refused"):
        lines.extend(["", f"Refusal: {refusal.get('reason')}"])
    questions = payload.get("author_questions") if isinstance(payload.get("author_questions"), list) else []
    if questions:
        lines.extend(["", "Author questions:"])
        for item in questions:
            if isinstance(item, dict):
                lines.append(f"  - {item.get('question')} ({item.get('why_user_owned')})")
    return "\n".join(lines)
