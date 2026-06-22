from __future__ import annotations

import re
from typing import Any

_CONTRACT_ID_RE = re.compile(r"\b(?P<id>claim-\d{3}|RW\d+|[CEQSFT]\d+)\b", re.IGNORECASE)
_PLAN_REAPPROVAL_RE = re.compile(
    r"\b("
    r"new\s+(major\s+)?(claim|contribution)|"
    r"stronger\s+(comparative|causal|novelty|generalization)|"
    r"strengthen\s+(the\s+)?(claim|wording)|"
    r"evaluation\s+scope\s+change|"
    r"plan\s+revision|"
    r"re-approval|reapproval|"
    r"beyond\s+the\s+approved\s+plan"
    r")\b",
    re.IGNORECASE,
)


def contract_refs_for_text(*values: Any) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {
        "claims": [],
        "evidence": [],
        "questions": [],
        "sections": [],
        "visuals": [],
        "related_work": [],
    }
    for value in values:
        for match in _CONTRACT_ID_RE.finditer(str(value or "")):
            ident = match.group("id")
            bucket = _bucket_for_id(ident)
            if ident not in refs[bucket]:
                refs[bucket].append(ident)
    return refs


def classify_contract_repair(*values: Any, automation: str | None = None) -> dict[str, Any]:
    text = " ".join(str(value or "") for value in values)
    plan_reapproval_required = bool(_PLAN_REAPPROVAL_RE.search(text))
    return {
        "repair_class": "approval_required_plan_change" if plan_reapproval_required else "contract_internal_repair",
        "plan_reapproval_required": plan_reapproval_required,
        "automation_scope": automation or "unknown",
    }


def contract_context_for_text(*values: Any, automation: str | None = None) -> dict[str, Any]:
    return {
        "contract_refs": contract_refs_for_text(*values),
        **classify_contract_repair(*values, automation=automation),
    }


def _bucket_for_id(ident: str) -> str:
    upper = ident.upper()
    if upper.startswith("RW"):
        return "related_work"
    if upper.startswith("Q"):
        return "questions"
    if upper.startswith("E"):
        return "evidence"
    if upper.startswith("S"):
        return "sections"
    if upper.startswith(("F", "T")):
        return "visuals"
    return "claims"


__all__ = ["classify_contract_repair", "contract_context_for_text", "contract_refs_for_text"]
